from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException

from core.settings import _CODE_ALPHABET, _CODE_PREFIX_MAP, _REDEEM_LOG_FILE
from core.utils import _append_jsonl, _parse_iso_datetime, _utc_iso
from services.data_store import _load_redeem_codes, _load_user_services, _save_redeem_codes, _save_user_services

def _generate_code(service_type: str = "", length: int = 8) -> str:
    prefix = _CODE_PREFIX_MAP.get(str(service_type).strip(), "X")
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    return f"{prefix}{body}"

def _generate_unique_code(codes: dict, service_type: str = "", length: int = 8, max_retries: int = 20) -> str:
    for _ in range(max_retries):
        code = _generate_code(service_type, length)
        if code not in codes:
            return code
    raise RuntimeError("卡密生成碰撞次数过多，请检查库存量")

def _append_redeem_log(payload: dict) -> None:
    _append_jsonl(_REDEEM_LOG_FILE, payload)

def _redeem_code_core(raw_code: str, user_id: str, source: str, extra_log: Optional[dict] = None) -> dict:
    code = str(raw_code or "").strip().upper()
    account = str(user_id or "").strip().lower()
    redeem_source = str(source or "").strip() or "unknown"
    if not code:
        raise HTTPException(status_code=400, detail="请填写卡密")
    if not account:
        raise HTTPException(status_code=400, detail="请填写账号或手机号")

    codes = _load_redeem_codes()
    item = codes.get(code)
    log_payload = {
        "id": f"RD-{uuid4().hex[:10]}",
        "created_at_utc": _utc_iso(),
        "code": code,
        "user_id": account,
        "source": redeem_source,
    }
    if isinstance(extra_log, dict):
        log_payload.update(extra_log)

    if not item:
        log_payload["result"] = "invalid"
        _append_redeem_log(log_payload)
        return {"ok": False, "status": "invalid", "message": "无效"}

    expires_at = str(item.get("expires_at", "")).strip()
    expire_dt = _parse_iso_datetime(expires_at)

    if item.get("status") == "used":
        log_payload["result"] = "used"
        _append_redeem_log(log_payload)
        return {"ok": False, "status": "used", "message": "已使用"}

    if expire_dt is not None and datetime.now(timezone.utc) > expire_dt:
        log_payload["result"] = "expired"
        _append_redeem_log(log_payload)
        return {"ok": False, "status": "expired", "message": "已过期"}

    service = item.get("service", {})
    user_services = _load_user_services()
    entry = user_services.setdefault(
        account,
        {"membership_until": None, "balance": 0, "quota": 0, "rewards": []},
    )

    granted: dict[str, object] = {
        "type": service.get("type", ""),
        "name": service.get("name", ""),
        "code": code,
        "granted_at_utc": _utc_iso(),
    }
    service_type = str(service.get("type", "")).strip()
    now = datetime.now(timezone.utc)
    if service_type == "membership":
        days = int(service.get("days", 0) or 0)
        until = now
        prev = _parse_iso_datetime(str(entry.get("membership_until", "")))
        if prev and prev > now:
            until = prev
        until = until + timedelta(days=days)
        entry["membership_until"] = until.isoformat()
        granted["membership_until"] = until.isoformat()
    elif service_type == "balance":
        amount = int(service.get("amount", 0) or 0)
        entry["balance"] = int(entry.get("balance", 0) or 0) + amount
        granted["balance_added"] = amount
        granted["balance_total"] = entry["balance"]
    elif service_type == "quota":
        amount = int(service.get("amount", 0) or 0)
        entry["quota"] = int(entry.get("quota", 0) or 0) + amount
        granted["quota_added"] = amount
        granted["quota_total"] = entry["quota"]
    entry.setdefault("rewards", []).append(granted)
    user_services[account] = entry
    _save_user_services(user_services)

    item["status"] = "used"
    item["used_at_utc"] = _utc_iso()
    item["used_by"] = account
    item["used_source"] = redeem_source
    codes[code] = item
    _save_redeem_codes(codes)

    log_payload["result"] = "success"
    log_payload["service"] = service
    _append_redeem_log(log_payload)
    result: dict = {
        "ok": True,
        "status": "success",
        "message": "成功",
        "service": service,
        "granted": granted,
    }
    if item.get("callback_url"):
        result["_callback_url"] = str(item["callback_url"])
        result["_order_id"] = str(item.get("order_id", ""))
    return result
