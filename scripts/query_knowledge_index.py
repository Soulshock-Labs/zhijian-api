#!/usr/bin/env python3
"""
简单检索知识库索引：
示例：
python3 scripts/query_knowledge_index.py --query 环境创设 --profile vip_custom --limit 10
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_FILE = BASE_DIR / "knowledge_base" / "indexes" / "knowledge_index.json"
ROUTE_FILE = BASE_DIR / "knowledge_base" / "indexes" / "profile_routes.json"
PROFILE_REGISTRY_FILE = BASE_DIR / "knowledge_base" / "profiles" / "profile_registry.json"
USER_REGISTRY_FILE = BASE_DIR / "knowledge_base" / "profiles" / "user_registry.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_profile_registry() -> dict[str, dict]:
    raw = _load_json(PROFILE_REGISTRY_FILE)
    if isinstance(raw, list):
        out = {}
        for item in raw:
            if isinstance(item, dict) and item.get("id"):
                out[str(item["id"])] = item
        return out
    return {}


def _infer_profile(role: str, is_vip: bool, years: int) -> str:
    r = (role or "").strip().lower()
    if is_vip:
        return "vip_custom"
    if "园长" in r or "admin" in r or "leader" in r:
        return "principal_view"
    if years >= 5:
        return "experienced_teacher"
    return "new_teacher"


def _load_user_registry() -> dict:
    raw = _load_json(USER_REGISTRY_FILE)
    if isinstance(raw, dict):
        users = raw.get("users")
        if isinstance(users, dict):
            return raw
    return {"version": "user-registry-v1", "users": {}}


def _upsert_user_profile(
    user_id: str,
    role: str,
    kindergarten_feature: str,
    years: int,
    is_vip: bool,
) -> dict:
    registry = _load_user_registry()
    users = registry.setdefault("users", {})
    uid = (user_id or "").strip()
    if not uid:
        return {}
    existing = users.get(uid, {}) if isinstance(users.get(uid), dict) else {}
    profile_id = str(existing.get("profile_id", "")).strip() or _infer_profile(role, is_vip, years)
    record = {
        "user_id": uid,
        "role": role or existing.get("role", "teacher"),
        "kindergarten_feature": kindergarten_feature or existing.get("kindergarten_feature", ""),
        "experience_years": int(years if years >= 0 else existing.get("experience_years", 0) or 0),
        "is_vip": bool(is_vip if is_vip is not None else existing.get("is_vip", False)),
        "profile_id": profile_id,
        "updated_at_utc": _now_iso(),
    }
    if not existing:
        record["created_at_utc"] = _now_iso()
    else:
        record["created_at_utc"] = existing.get("created_at_utc", _now_iso())
    users[uid] = record
    _save_json(USER_REGISTRY_FILE, registry)
    return record


def _score(query: str, rec: dict, profile_pref: set[str]) -> int:
    text = f"{rec.get('filename', '')} {rec.get('excerpt', '')}"
    s = 0
    for token in [x for x in query.split() if x]:
        s += text.count(token) * 5
    tags = set(rec.get("tags", []))
    s += len(tags & profile_pref) * 6
    s += rec.get("feature_counts", {}).get("national_standard", 0)
    s += int(rec.get("source_priority", 0))
    return s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="", help="关键词，用空格分词")
    parser.add_argument("--profile", default="", help="画像ID，例如 vip_custom")
    parser.add_argument("--user-id", default="", help="用户ID；不存在将自动建档")
    parser.add_argument("--role", default="teacher", help="用户角色，如 teacher/principal")
    parser.add_argument("--experience-years", type=int, default=0, help="从业年限")
    parser.add_argument("--kindergarten-feature", default="", help="园本特色关键词")
    parser.add_argument("--vip", action="store_true", help="是否 VIP 用户")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    index = _load_json(INDEX_FILE)
    route = _load_json(ROUTE_FILE).get("profile_routes", {})
    profile_registry = _load_profile_registry()

    resolved_profile = args.profile.strip()
    if args.user_id.strip():
        user_record = _upsert_user_profile(
            user_id=args.user_id.strip(),
            role=args.role.strip(),
            kindergarten_feature=args.kindergarten_feature.strip(),
            years=max(0, int(args.experience_years or 0)),
            is_vip=bool(args.vip),
        )
        if not resolved_profile:
            resolved_profile = str(user_record.get("profile_id", "")).strip()
        print(
            f"[user] user_id={user_record.get('user_id')} profile={user_record.get('profile_id')} "
            f"role={user_record.get('role')} years={user_record.get('experience_years')}"
        )

    if resolved_profile and resolved_profile not in profile_registry:
        print(f"[warn] 未找到画像 {resolved_profile}，回退为通用检索")
        resolved_profile = ""

    records = index.get("records", [])
    if not records:
        print("未找到索引数据，请先执行 python3 scripts/rebuild_knowledge_index.py")
        return

    profile_pref = set()
    if resolved_profile and route.get(resolved_profile):
        ids = {x.get("doc_id") for x in route.get(resolved_profile, [])}
        for r in records:
            if r.get("doc_id") in ids:
                profile_pref.update(r.get("tags", []))

    ranked = sorted(
        records,
        key=lambda rec: _score(args.query, rec, profile_pref),
        reverse=True,
    )
    for idx, rec in enumerate(ranked[: max(1, args.limit)], 1):
        print(
            f"{idx:02d}. [{rec.get('primary_bucket','mixed')}] [{rec.get('source_tier','incoming')}] {rec.get('filename')} "
            f"tags={','.join(rec.get('tags', []))}"
        )
        print(f"    path={rec.get('path')}")
        print(f"    excerpt={rec.get('excerpt','')}")


if __name__ == "__main__":
    main()
