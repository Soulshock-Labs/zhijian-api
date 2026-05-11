from __future__ import annotations

import json

from core.settings import (
    _ACCOUNT_INDEX_FILE,
    APP_ENV,
    _APP_STATS_FILE,
    _DEFAULT_APP_STATS,
    _DEFAULT_REDEEM_CODES,
    _DEFAULT_TEMPLATE_STATS,
    _KNOWLEDGE_BASE_DIR,
    _KNOWLEDGE_INDEX_FILE,
    _KNOWLEDGE_ROUTE_FILE,
    _MEMBER_NO_FILE,
    _REDEEM_CODES_FILE,
    _REDEEM_CODES_GCS_URI,
    _REGISTER_LOG_FILE,
    _TEMPLATE_STATS_FILE,
    _USER_ACCOUNTS_FILE,
    _USER_SERVICE_FILE,
    _WEBHOOK_RETRY_FILE,
)
from core.state import FIRESTORE_ENABLED, _fs, logger
from core.utils import _parse_gs_uri, _read_json_file


def _merge_string_dicts(remote: dict[str, str], local: dict[str, str]) -> dict[str, str]:
    out = dict(remote)
    out.update(local)
    return out


def _merge_object_dicts(remote: dict[str, dict], local: dict[str, dict]) -> dict[str, dict]:
    out = {k: dict(v) for k, v in remote.items()}
    for key, value in local.items():
        if isinstance(value, dict):
            out[key] = dict(value)
    return out

def _load_template_stats() -> dict[str, int]:
    if not _TEMPLATE_STATS_FILE.exists():
        return dict(_DEFAULT_TEMPLATE_STATS)
    try:
        data = json.loads(_TEMPLATE_STATS_FILE.read_text(encoding="utf-8"))
        out = dict(_DEFAULT_TEMPLATE_STATS)
        if isinstance(data, dict):
            for k in out:
                v = data.get(k, 0)
                out[k] = int(v) if isinstance(v, (int, float, str)) else 0
        return out
    except Exception:
        return dict(_DEFAULT_TEMPLATE_STATS)

def _load_app_stats() -> dict[str, int]:
    if not _APP_STATS_FILE.exists():
        return dict(_DEFAULT_APP_STATS)
    try:
        data = json.loads(_APP_STATS_FILE.read_text(encoding="utf-8"))
        out = dict(_DEFAULT_APP_STATS)
        if isinstance(data, dict):
            for k in out:
                out[k] = int(data.get(k, out[k]) or 0)
        return out
    except Exception:
        return dict(_DEFAULT_APP_STATS)

def _save_app_stats(stats: dict[str, int]) -> None:
    try:
        _APP_STATS_FILE.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("保存应用统计失败：%s", e)

def _inc_app_stat(key: str, delta: int = 1) -> dict[str, int]:
    stats = _load_app_stats()
    if key not in stats:
        stats[key] = 0
    stats[key] = max(0, int(stats.get(key, 0)) + int(delta))
    _save_app_stats(stats)
    return stats

def _save_template_stats(stats: dict[str, int]) -> None:
    try:
        _TEMPLATE_STATS_FILE.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # 计数写入失败不影响主流程下载
        pass

def _inc_template_download(template_id: str) -> dict[str, int]:
    stats = _load_template_stats()
    if template_id not in stats:
        stats[template_id] = 0
    stats[template_id] += 1
    _save_template_stats(stats)
    return stats

def _load_registered_ids() -> set[str]:
    ids: set[str] = set()
    if not _REGISTER_LOG_FILE.exists():
        return ids
    try:
        for line in _REGISTER_LOG_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            rid = str(row.get("identifier", "")).strip().lower()
            if rid:
                ids.add(rid)
    except Exception as e:
        logger.warning("读取注册记录失败：%s", e)
    return ids

def _redeem_codes_dict_from_json_list(raw: object) -> dict[str, dict]:
    items = raw if isinstance(raw, list) else []
    out: dict[str, dict] = {}
    for item in items:
        if isinstance(item, dict) and item.get("code"):
            out[str(item["code"]).strip().upper()] = dict(item)
    return out

def _merge_redeem_row(a: dict, b: dict) -> dict:
    """合并两条卡密：任一侧为已使用则保留已使用，避免并发核销互相覆盖。"""
    sa = str(a.get("status", "")).strip().lower()
    sb = str(b.get("status", "")).strip().lower()
    if sa == "used" and sb != "used":
        return dict(a)
    if sb == "used" and sa != "used":
        return dict(b)
    if sa == "used" and sb == "used":
        ta = str(a.get("used_at_utc", ""))
        tb = str(b.get("used_at_utc", ""))
        return dict(a) if ta >= tb else dict(b)
    return dict(b)

def _merge_redeem_dicts(remote: dict[str, dict], local: dict[str, dict]) -> dict[str, dict]:
    keys = set(remote) | set(local)
    out: dict[str, dict] = {}
    for k in keys:
        if k in remote and k in local:
            out[k] = _merge_redeem_row(remote[k], local[k])
        elif k in remote:
            out[k] = dict(remote[k])
        else:
            out[k] = dict(local[k])
    return out

def _try_load_redeem_codes_gcs() -> dict[str, dict] | None:
    """从 GCS 读取卡密库；对象不存在返回 None（由调用方回退本地）。"""
    if not _REDEEM_CODES_GCS_URI:
        return None
    try:
        from google.cloud import storage  # noqa: PLC0415
    except ImportError:
        logger.warning("已设置 REDEEM_CODES_GCS_URI 但未安装 google-cloud-storage，跳过 GCS")
        return None
    try:
        bucket_name, blob_name = _parse_gs_uri(_REDEEM_CODES_GCS_URI)
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            return None
        raw = json.loads(blob.download_as_text(encoding="utf-8"))
        return _redeem_codes_dict_from_json_list(raw)
    except Exception as e:
        logger.warning("从 GCS 读取卡密库失败：%s", e)
        return None

def _save_redeem_codes_gcs_merged(incoming: dict[str, dict]) -> dict[str, dict] | None:
    """将 incoming 与 GCS 当前内容合并后写回；带乐观锁重试。成功返回合并后的全量 dict。"""
    try:
        from google.api_core import exceptions as gexc  # noqa: PLC0415
        from google.cloud import storage  # noqa: PLC0415
    except ImportError:
        logger.warning("无法写入 GCS：缺少 google-cloud-storage")
        return None
    bucket_name, blob_name = _parse_gs_uri(_REDEEM_CODES_GCS_URI)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    for attempt in range(16):
        try:
            remote: dict[str, dict] = {}
            gen: int | None = None
            if blob.exists():
                blob.reload()
                gen = blob.generation
                raw = json.loads(blob.download_as_text(encoding="utf-8"))
                remote = _redeem_codes_dict_from_json_list(raw)
            merged = _merge_redeem_dicts(remote, incoming)
            payload = json.dumps(list(merged.values()), ensure_ascii=False, indent=2)
            if gen is not None:
                blob.upload_from_string(
                    payload,
                    content_type="application/json; charset=utf-8",
                    if_generation_match=gen,
                )
            else:
                blob.upload_from_string(payload, content_type="application/json; charset=utf-8")
            return merged
        except gexc.PreconditionFailed:
            continue
        except Exception as e:
            logger.warning("写入 GCS 卡密库失败（第 %s 次）：%s", attempt + 1, e)
            if attempt >= 15:
                return None
    return None

def _load_redeem_codes() -> dict[str, dict]:
    if _REDEEM_CODES_GCS_URI:
        gcs_data = _try_load_redeem_codes_gcs()
        if gcs_data is not None:
            return gcs_data
        logger.info("GCS 卡密库不存在或暂不可读，回退本地 redeem_codes.json")

    if not _REDEEM_CODES_FILE.exists():
        if APP_ENV == "production":
            raise RuntimeError("生产环境缺少 redeem_codes.json，已拒绝加载默认卡密")
        try:
            _REDEEM_CODES_FILE.write_text(
                json.dumps(_DEFAULT_REDEEM_CODES, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("初始化卡密库失败：%s", e)
            return {item["code"]: dict(item) for item in _DEFAULT_REDEEM_CODES}

    try:
        raw = json.loads(_REDEEM_CODES_FILE.read_text(encoding="utf-8"))
        return _redeem_codes_dict_from_json_list(raw)
    except Exception as e:
        logger.warning("读取卡密库失败：%s", e)
        return {item["code"]: dict(item) for item in _DEFAULT_REDEEM_CODES}

def _save_redeem_codes(codes: dict[str, dict]) -> None:
    to_write: dict[str, dict] = dict(codes)
    if _REDEEM_CODES_GCS_URI:
        merged = _save_redeem_codes_gcs_merged(codes)
        if merged is not None:
            to_write = merged
        else:
            logger.warning("GCS 卡密库写入失败，仅写本地副本（多实例下可能不一致）")
    try:
        _REDEEM_CODES_FILE.write_text(
            json.dumps(list(to_write.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("保存卡密库失败：%s", e)

def _load_user_services() -> dict[str, dict]:
    """读用户服务：合并 Firestore 与本地 JSON，本地优先。"""
    remote: dict[str, dict] = {}
    if FIRESTORE_ENABLED:
        try:
            docs = _fs().collection("user_services").stream()
            for doc in docs:
                data = doc.to_dict()
                if isinstance(data, dict):
                    remote[doc.id] = data
        except Exception as e:
            logger.warning("Firestore 读取用户服务失败，回退本地：%s", e)
    local: dict[str, dict] = {}
    if not _USER_SERVICE_FILE.exists():
        return remote
    try:
        data = json.loads(_USER_SERVICE_FILE.read_text(encoding="utf-8"))
        local = data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("读取用户服务失败：%s", e)
    return _merge_object_dicts(remote, local)

def _save_user_services(data: dict[str, dict]) -> None:
    """写用户服务：同时写 Firestore 和本地 JSON（双保险）。"""
    # 写 Firestore
    if FIRESTORE_ENABLED:
        try:
            batch = _fs().batch()
            col = _fs().collection("user_services")
            for user_id, entry in data.items():
                batch.set(col.document(user_id), entry)
            batch.commit()
        except Exception as e:
            logger.warning("Firestore 写用户服务失败：%s", e)
    # 写本地 JSON 兜底
    try:
        _USER_SERVICE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("保存用户服务失败：%s", e)

def _load_webhook_retries() -> list[dict]:
    if not _WEBHOOK_RETRY_FILE.exists():
        return []
    items: list[dict] = []
    try:
        for line in _WEBHOOK_RETRY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
    except Exception as e:
        logger.warning("读取 Webhook 重试队列失败：%s", e)
    return items

def _save_webhook_retries(items: list[dict]) -> None:
    try:
        _WEBHOOK_RETRY_FILE.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in items),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("保存 Webhook 重试队列失败：%s", e)

def _enqueue_webhook_retry(payload: dict) -> None:
    items = _load_webhook_retries()
    items.append(payload)
    _save_webhook_retries(items)

def _load_user_accounts() -> dict[str, dict]:
    """读用户账户：合并 Firestore 与本地 JSON，本地优先。"""
    remote: dict[str, dict] = {}
    if FIRESTORE_ENABLED:
        try:
            docs = _fs().collection("users").stream()
            for doc in docs:
                data = doc.to_dict()
                if isinstance(data, dict):
                    remote[doc.id] = data
        except Exception as e:
            logger.warning("Firestore 读取用户账户失败，回退本地：%s", e)
    local: dict[str, dict] = {}
    if not _USER_ACCOUNTS_FILE.exists():
        return remote
    try:
        data = json.loads(_USER_ACCOUNTS_FILE.read_text(encoding="utf-8"))
        local = data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("读取用户账户失败：%s", e)
    return _merge_object_dicts(remote, local)

def _load_user_account(account_id: str) -> dict | None:
    """按 account_id 读取单个用户账户，避免全表扫描。"""
    remote: dict | None = None
    if FIRESTORE_ENABLED:
        try:
            doc = _fs().collection("users").document(account_id).get()
            if doc.exists:
                data = doc.to_dict()
                if isinstance(data, dict):
                    remote = data
        except Exception as e:
            logger.warning("Firestore 读取单个用户账户失败，回退本地：%s", e)

    local: dict | None = None
    if _USER_ACCOUNTS_FILE.exists():
        try:
            data = json.loads(_USER_ACCOUNTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                entry = data.get(account_id)
                if isinstance(entry, dict):
                    local = entry
        except Exception as e:
            logger.warning("读取本地单个用户账户失败：%s", e)

    if remote and local:
        merged = dict(remote)
        merged.update(local)
        return merged
    return local or remote

def _save_user_account(account_id: str, entry: dict) -> None:
    """写单个用户账户，避免每次注册都批量回写整库。"""
    if FIRESTORE_ENABLED:
        try:
            _fs().collection("users").document(account_id).set(entry, merge=True)
        except Exception as e:
            logger.warning("Firestore 写单个用户账户失败：%s", e)
    try:
        data: dict[str, dict] = {}
        if _USER_ACCOUNTS_FILE.exists():
            raw = json.loads(_USER_ACCOUNTS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        data[account_id] = entry
        _USER_ACCOUNTS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("保存单个用户账户失败：%s", e)

def _save_user_accounts(data: dict[str, dict]) -> None:
    """写用户账户：同时写 Firestore 和本地 JSON（双保险）。"""
    if FIRESTORE_ENABLED:
        try:
            batch = _fs().batch()
            col = _fs().collection("users")
            for uid, entry in data.items():
                batch.set(col.document(uid), entry, merge=True)
            batch.commit()
        except Exception as e:
            logger.warning("Firestore 写用户账户失败：%s", e)
    try:
        _USER_ACCOUNTS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("保存用户账户失败：%s", e)

# ══════════════════════════════════════════════════════════════════════
# 账号索引：phone / openid → account_id 反查表
# ══════════════════════════════════════════════════════════════════════

def _load_account_index() -> dict[str, str]:
    """
    读取反查索引。结构：
    {
      "phone:13800138000": "uid_xxx",
      "openid:wx_yyy":     "uid_xxx",
    }
    """
    remote: dict[str, str] = {}
    if FIRESTORE_ENABLED:
        try:
            doc = _fs().collection("meta").document("account_index").get()
            if doc.exists:
                data = doc.to_dict() or {}
                remote = {k: v for k, v in data.items() if isinstance(v, str)}
        except Exception as e:
            logger.warning("Firestore 读取 account_index 失败，回退本地：%s", e)
    local: dict[str, str] = {}
    if not _ACCOUNT_INDEX_FILE.exists():
        return remote
    try:
        data = json.loads(_ACCOUNT_INDEX_FILE.read_text(encoding="utf-8"))
        local = data if isinstance(data, dict) else {}
    except Exception:
        local = {}
    return _merge_string_dicts(remote, local)


def _save_account_index(index: dict[str, str]) -> None:
    if FIRESTORE_ENABLED:
        try:
            _fs().collection("meta").document("account_index").set(index)
        except Exception as e:
            logger.warning("Firestore 写 account_index 失败：%s", e)
    try:
        _ACCOUNT_INDEX_FILE.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("保存 account_index 失败：%s", e)


# ══════════════════════════════════════════════════════════════════════
# 会员号计数器（6位递增，从 10000 起）
# ══════════════════════════════════════════════════════════════════════

_MEMBER_NO_START = 60001


def _max_existing_member_no() -> int:
    """扫描账号索引，返回已存在的最大会员号。"""
    try:
        index = _load_account_index()
    except Exception as e:
        logger.warning("读取现有会员号失败，跳过高水位校准：%s", e)
        return _MEMBER_NO_START - 1

    max_no = _MEMBER_NO_START - 1
    for key in index.keys():
        if not str(key).startswith("member_no:"):
            continue
        try:
            member_no = int(str(key).split(":", 1)[1].strip())
        except Exception:
            continue
        if member_no >= _MEMBER_NO_START:
            max_no = max(max_no, member_no)
    return max_no


def _next_member_no() -> str:
    """生成下一个会员号（递增，线程安全靠单进程 Cloud Run 保证）。"""
    existing_max = _max_existing_member_no()

    if FIRESTORE_ENABLED:
        try:
            ref = _fs().collection("meta").document("member_no_counter")
            from google.cloud.firestore import Client  # noqa: F401
            # Firestore 事务递增
            @_fs().transaction()  # type: ignore[misc]
            def _tx(transaction, ref):  # type: ignore[misc]
                snap = ref.get(transaction=transaction)
                current = int(snap.get("value")) if snap.exists and snap.get("value") is not None else _MEMBER_NO_START - 1
                current = max(current, _MEMBER_NO_START - 1, existing_max)
                next_no = current + 1
                transaction.set(ref, {"value": next_no})
                return next_no
            no = _tx(ref)  # type: ignore[call-arg]
            return str(no)
        except Exception as e:
            logger.warning("Firestore 会员号递增失败，回退本地：%s", e)

    # 本地文件计数器
    try:
        if _MEMBER_NO_FILE.exists():
            current = int(json.loads(_MEMBER_NO_FILE.read_text(encoding="utf-8")).get("value", _MEMBER_NO_START - 1))
        else:
            current = _MEMBER_NO_START - 1
        current = max(current, _MEMBER_NO_START - 1, existing_max)
        next_no = current + 1
        _MEMBER_NO_FILE.write_text(
            json.dumps({"value": next_no}, ensure_ascii=False), encoding="utf-8"
        )
        return str(next_no)
    except Exception as e:
        logger.warning("会员号计数器失败，使用随机备用：%s", e)
        import random
        return str(random.randint(10000, 99999))


def _knowledge_base_status() -> dict:
    index_payload = _read_json_file(_KNOWLEDGE_INDEX_FILE)
    route_payload = _read_json_file(_KNOWLEDGE_ROUTE_FILE)
    records = index_payload.get("records", [])
    bucket_counts = index_payload.get("buckets", {})
    source_counts: dict[str, int] = {}
    if isinstance(records, list):
        for item in records:
            if not isinstance(item, dict):
                continue
            tier = str(item.get("source_tier", "unknown") or "unknown")
            source_counts[tier] = source_counts.get(tier, 0) + 1

    routes = route_payload.get("profile_routes", {})
    profile_count = len(routes) if isinstance(routes, dict) else 0
    generated_at = (
        str(index_payload.get("generated_at_utc", "")).strip()
        or str(route_payload.get("generated_at_utc", "")).strip()
    )
    return {
        "enabled": _KNOWLEDGE_BASE_DIR.exists(),
        "doc_count": int(index_payload.get("doc_count", 0) or 0),
        "bucket_counts": bucket_counts if isinstance(bucket_counts, dict) else {},
        "source_counts": source_counts,
        "profile_route_count": profile_count,
        "generated_at_utc": generated_at,
        "index_ready": bool(index_payload),
    }
