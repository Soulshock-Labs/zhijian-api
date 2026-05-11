"""
services/user_service.py — 账号核心逻辑
==========================================
账号数据模型：
  account_id   : "uid_" + uuid hex（永不变，系统主键）
  member_no    : "10000" 起递增（永不变，对外展示）
  phone        : 手机号（唯一索引，可迁移）
  openid       : 微信 openid（唯一索引，可空）
  password_hash: SHA-256（Web/Android 登录）
  role         : teacher / org_admin / platform_admin
  org_id       : 所属园所 ID
  active_tokens: 多端 token 列表（最多 5 个）

反查索引（account_index.json）：
  "phone:13800138000" → "uid_xxx"
  "openid:wx_yyy"     → "uid_xxx"
  "token:ut_zzz"      → "uid_xxx"    ← 快速 token 验证
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException

from core.state import FIRESTORE_ENABLED, _fs, logger
from core.utils import _utc_iso
from services.data_store import (
    _load_account_index,
    _load_user_account,
    _load_user_accounts,
    _next_member_no,
    _save_account_index,
    _save_user_account,
    _save_user_accounts,
)

# 每个用户最多同时保留的 token 数
_MAX_TOKENS = 5

# ══════════════════════════════════════════════════════════════════════
# 内部工具
# ══════════════════════════════════════════════════════════════════════

def _new_account_id() -> str:
    return f"uid_{uuid4().hex}"


def _new_token() -> str:
    return f"ut_{uuid4().hex}"


def _index_key_phone(phone: str) -> str:
    return f"phone:{phone.strip().lower()}"


def _index_key_member_no(member_no: str) -> str:
    return f"member_no:{member_no.strip()}"


def _index_key_openid(openid: str) -> str:
    return f"openid:{openid.strip()}"


def _index_key_token(token: str) -> str:
    return f"token:{token.strip()}"


# ══════════════════════════════════════════════════════════════════════
# 索引维护
# ══════════════════════════════════════════════════════════════════════

def _index_add_token(index: dict, account_id: str, tokens: list[str]) -> None:
    """把 active_tokens 列表全部写入索引（旧 token key 会留着，无害）。"""
    for t in tokens:
        if t:
            index[_index_key_token(t)] = account_id


def _rebuild_index_for_account(index: dict, account: dict) -> None:
    """用单条 account 数据刷新索引中的所有 key。"""
    aid = account["account_id"]
    if account.get("phone"):
        index[_index_key_phone(account["phone"])] = aid
    if account.get("openid"):
        index[_index_key_openid(account["openid"])] = aid
    if account.get("member_no"):
        index[_index_key_member_no(account["member_no"])] = aid
    _index_add_token(index, aid, account.get("active_tokens") or [])


# ══════════════════════════════════════════════════════════════════════
# Token 管理
# ══════════════════════════════════════════════════════════════════════

def _add_token(account: dict, index: dict, token: str) -> None:
    """
    追加新 token，超出上限时淘汰最旧的，同步更新索引。
    account 和 index 是引用，调用方负责持久化。
    """
    tokens: list[str] = list(account.get("active_tokens") or [])
    if token not in tokens:
        tokens.append(token)
    if len(tokens) > _MAX_TOKENS:
        tokens = tokens[-_MAX_TOKENS:]
    account["active_tokens"] = tokens
    account["last_token"] = token          # 向后兼容旧字段
    index[_index_key_token(token)] = account["account_id"]


# ══════════════════════════════════════════════════════════════════════
# 兼容旧数据：把 phone/openid 主键账号迁移为新结构
# ══════════════════════════════════════════════════════════════════════

def _migrate_legacy_account(old_key: str, entry: dict) -> dict:
    """
    把旧格式（主键是 phone 或 openid）的账号转成新格式。
    新 account_id = uid_xxx，old_key 写进 phone 或 openid 字段。
    """
    now = _utc_iso()
    # 判断 old_key 类型
    is_openid = old_key.startswith("dev_") or (
        not old_key.replace("+", "").replace("-", "").isdigit()
        and len(old_key) > 10
        and not "@" in old_key
    )
    new_entry = dict(entry)
    new_entry.setdefault("account_id",    _new_account_id())
    new_entry.setdefault("member_no",     _next_member_no())
    new_entry.setdefault("role",          "teacher")
    new_entry.setdefault("org_id",        "")
    new_entry.setdefault("active_tokens", [])
    new_entry.setdefault("created_at_utc", now)
    new_entry.setdefault("updated_at_utc", now)

    if is_openid:
        new_entry.setdefault("openid", old_key)
        new_entry.setdefault("phone",  "")
    else:
        new_entry.setdefault("phone",  old_key)
        new_entry.setdefault("openid", "")

    # 兼容旧 last_token → active_tokens
    last = entry.get("last_token", "")
    if last and last not in new_entry["active_tokens"]:
        new_entry["active_tokens"].append(last)

    return new_entry


def _ensure_new_format(accounts: dict, index: dict) -> bool:
    """
    检查 accounts 里是否有旧格式账号，如有则原地迁移。
    返回 True 表示发生了迁移（调用方需要保存）。
    """
    changed = False
    new_accounts: dict[str, dict] = {}

    for key, entry in accounts.items():
        if key.startswith("uid_"):
            # 已是新格式，直接保留
            new_accounts[key] = entry
        else:
            # 旧格式，迁移
            migrated = _migrate_legacy_account(key, entry)
            aid = migrated["account_id"]
            new_accounts[aid] = migrated
            _rebuild_index_for_account(index, migrated)
            logger.info("账号已迁移：%s → %s (member_no=%s)", key, aid, migrated["member_no"])
            changed = True

    if changed:
        accounts.clear()
        accounts.update(new_accounts)

    return changed


# ══════════════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════════════

def _get_or_create_user(openid: str) -> dict:
    """微信登录：用 openid 查账号，不存在时创建。返回 account dict。"""
    accounts = _load_user_accounts()
    index    = _load_account_index()
    _ensure_new_format(accounts, index)

    aid = index.get(_index_key_openid(openid))
    if aid and aid in accounts:
        return accounts[aid]

    # 创建新账号
    now   = _utc_iso()
    aid   = _new_account_id()
    mno   = _next_member_no()
    entry: dict = {
        "account_id":    aid,
        "member_no":     mno,
        "phone":         "",
        "openid":        openid,
        "password_hash": "",
        "role":          "teacher",
        "org_id":        "",
        "active_tokens": [],
        "last_token":    None,
        "agent_profile": {
            "name":        "小助手",
            "personality": "热心、耐心",
            "tone":        "亲切温暖",
            "style":       "鼓励式教学",
        },
        "created_at_utc": now,
        "updated_at_utc": now,
    }
    accounts[aid] = entry
    index[_index_key_openid(openid)] = aid
    _save_user_accounts(accounts)
    _save_account_index(index)
    logger.info("新账号（微信）：aid=%s member_no=%s openid=%s", aid, mno, openid)
    return entry


def _create_account(password_hash: str, member_no: str = "", role: str = "teacher") -> dict:
    """
    注册：只需密码，系统自动分配会员号。
    member_no 可手动指定（测试用），不指定则自动递增。
    """
    index    = _load_account_index()

    now = _utc_iso()
    aid = _new_account_id()
    requested_member_no = member_no.strip()

    if requested_member_no:
        mno = requested_member_no
        if _index_key_member_no(mno) in index:
            raise HTTPException(status_code=409, detail=f"会员号 {mno} 已存在")
    else:
        mno = ""
        for _ in range(50):
            candidate = _next_member_no()
            if _index_key_member_no(candidate) not in index:
                mno = candidate
                break
        if not mno:
            raise HTTPException(status_code=500, detail="会员号分配失败，请稍后重试")

    entry: dict = {
        "account_id":     aid,
        "member_no":      mno,
        "phone":          "",       # 小程序绑定时填入
        "openid":         "",       # 小程序登录时填入
        "password_hash":  password_hash,
        "role":           role,
        "org_id":         "",
        "active_tokens":  [],
        "last_token":     None,
        "agent_profile":  {
            "name":        "小助手",
            "personality": "热心、耐心",
            "tone":        "亲切温暖",
            "style":       "鼓励式教学",
        },
        "created_at_utc": now,
        "updated_at_utc": now,
    }
    index[_index_key_member_no(mno)] = aid
    _save_user_account(aid, entry)
    _save_account_index(index)
    logger.info("新账号：aid=%s member_no=%s", aid, mno)
    return entry


def _get_account_by_phone(phone: str) -> dict | None:
    """按手机号查账号（小程序绑定用），不存在返回 None。"""
    index    = _load_account_index()

    aid = index.get(_index_key_phone(phone))
    if not aid:
        return None
    return _load_user_account(aid)


def _get_account_by_member_no(member_no: str) -> dict | None:
    """按会员号查账号（Web/Android 登录用），不存在返回 None。"""
    index    = _load_account_index()

    aid = index.get(_index_key_member_no(member_no.strip()))
    if not aid:
        return None
    return _load_user_account(aid)


def _generate_user_token(account_id: str) -> str:
    """生成 token（不写入，由调用方通过 _issue_token 写入）。"""
    return _new_token()


def _issue_token(account_id: str) -> str:
    """
    生成并写入 token，返回 token 字符串。
    同时更新 account.active_tokens 和 index。
    """
    account = _load_user_account(account_id)
    index    = _load_account_index()

    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    token = _new_token()
    _add_token(account, index, token)
    account["updated_at_utc"] = _utc_iso()

    _save_user_account(account_id, account)
    _save_account_index(index)
    return token


# 向后兼容：旧代码直接调 _generate_user_token + 手动写 last_token
# 新代码统一用 _issue_token
def _add_token_to_account(accounts: dict, account_id: str, token: str) -> None:
    """向后兼容旧调用方式（users.py 过渡期用）。"""
    index = _load_account_index()
    if account_id in accounts:
        _add_token(accounts[account_id], index, token)
        _save_account_index(index)


def _verify_user_token(token: str) -> str:
    """
    验证 token，返回 account_id。失败抛 401。
    查找顺序：index（快）→ 全表扫描（兜底）。
    """
    token = str(token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="请先登录（user_token 缺失）")

    # 1. 先查索引（O(1)）
    index = _load_account_index()
    aid   = index.get(_index_key_token(token))
    if aid:
        accounts = _load_user_accounts()
        if aid in accounts:
            entry = accounts[aid]
            if token in (entry.get("active_tokens") or []) or entry.get("last_token") == token:
                return aid

    # 2. Firestore 全表（索引未命中时兜底）
    if FIRESTORE_ENABLED:
        try:
            fs   = _fs()
            docs = fs.collection("users").where("active_tokens", "array_contains", token).limit(1).stream()
            for doc in docs:
                return doc.id
            docs = fs.collection("users").where("last_token", "==", token).limit(1).stream()
            for doc in docs:
                return doc.id
        except Exception as e:
            logger.warning("Firestore token 验证失败，回退本地：%s", e)

    # 3. 本地全表扫描（最终兜底）
    accounts = _load_user_accounts()
    for aid, entry in accounts.items():
        if token in (entry.get("active_tokens") or []):
            return aid
        if entry.get("last_token") == token:
            return aid

    raise HTTPException(status_code=401, detail="token 无效或已过期，请重新登录")


def _verify_user_token_full(token: str) -> dict:
    """验证 token，返回完整 account dict（含 role/member_no 等）。"""
    aid      = _verify_user_token(token)
    accounts = _load_user_accounts()
    entry    = accounts.get(aid)
    if not entry:
        raise HTTPException(status_code=401, detail="账号数据异常，请重新登录")
    return entry
