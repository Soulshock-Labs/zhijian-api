from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import asyncio
from datetime import datetime, timezone

from core.auth import require_permission
from core.settings import PARTNER_REDEEM_SOURCE, PARTNER_REDEEM_TOKENS, PARTNER_WEBHOOK_URLS
from core.state import logger
from core.utils import _parse_iso_datetime, _utc_iso
from services.data_store import _load_redeem_codes, _save_redeem_codes
from services.redeem_service import _generate_unique_code, _redeem_code_core
from services.webhook_service import _dispatch_webhook
router = APIRouter()
@router.get("/redeem-codes", tags=["兑换"])
async def redeem_codes(user_token: str):
    """仅平台管理员可查看卡密列表。"""
    require_permission(user_token, "manage_platform")
    codes = _load_redeem_codes()
    items = []
    for code, item in codes.items():
        items.append({
            "code": code,
            "status": item.get("status", "unused"),
            "expires_at": item.get("expires_at", ""),
            "description": item.get("description", ""),
            "service": item.get("service", {}),
        })
    return {"ok": True, "codes": items}
@router.get("/redeem/query", tags=["兑换"])
async def query_redeem_code(code: str):
    """
    只读查询卡密状态（不核销，不写入任何数据）。
    只返回 valid/used/expired/invalid 最小状态，不暴露账号信息。
    """
    normalized = str(code or "").strip().upper()
    if not normalized:
        raise HTTPException(status_code=400, detail="请填写卡密")

    codes = _load_redeem_codes()
    item = codes.get(normalized)

    if not item:
        return {"ok": False, "status": "invalid", "message": "无效卡密"}

    expires_at = str(item.get("expires_at", "")).strip()
    expire_dt = _parse_iso_datetime(expires_at)
    service = item.get("service", {})
    description = item.get("description", "")

    if item.get("status") == "used":
        return {
            "ok": False,
            "status": "used",
            "message": "已使用",
            "service": service,
            "description": description,
        }

    if expire_dt is not None and datetime.now(timezone.utc) > expire_dt:
        return {
            "ok": False,
            "status": "expired",
            "message": "已过期",
            "service": service,
            "description": description,
        }

    return {
        "ok": True,
        "status": "unused",
        "message": "未使用",
        "expires_at": expires_at,
        "service": service,
        "description": description,
    }
@router.post("/redeem", tags=["兑换"])
async def redeem_code(payload: dict = Body(...)):
    """
    卡密兑换闭环：
    - 验证是否有效
    - 验证是否已使用
    - 验证是否过期
    - 核销并发放对应服务
    - 如卡密携带 callback_url，异步通知第三方（含重试）
    """
    account = require_permission(str(payload.get("user_token", "")).strip(), "generate")
    code = str(payload.get("code", ""))
    result = _redeem_code_core(
        raw_code=code,
        user_id=str(account.get("account_id", "")).strip(),
        source=str(payload.get("source", "")) or "unknown",
    )
    if result.get("ok"):
        callback_url = result.pop("_callback_url", "")
        cb_order_id = result.pop("_order_id", "")
        if callback_url:
            webhook_body = {
                "event": "redeemed",
                "code": code.strip().upper(),
                "user_id": str(account.get("account_id", "")).strip().lower(),
                "order_id": cb_order_id,
                "redeemed_at_utc": _utc_iso(),
                "status": "redeemed",
                "channel": "user_self",
            }
            asyncio.create_task(_dispatch_webhook(callback_url, webhook_body, cb_order_id, code))
    else:
        result.pop("_callback_url", None)
        result.pop("_order_id", None)
    return result
@router.post("/partner/redeem", tags=["兑换"])
async def partner_redeem(
    payload: dict = Body(...),
    x_partner_token: str = Header(default="", alias="X-Partner-Token"),
):
    """
    第三方商城兑换入口（服务端对服务端）：
    - Header 鉴权（X-Partner-Token）
    - 复用本系统同一套核销逻辑，避免双轨不一致
    - 核销成功后异步回调第三方 Webhook（含重试）
    """
    if not PARTNER_REDEEM_TOKENS:
        raise HTTPException(status_code=503, detail="第三方兑换入口未启用")

    provided = str(x_partner_token or payload.get("partner_token", "")).strip()
    if provided not in PARTNER_REDEEM_TOKENS:
        raise HTTPException(status_code=401, detail="无效的 partner token")

    code = str(payload.get("code", ""))
    order_id = str(payload.get("order_id", "")).strip()
    source = str(payload.get("source", "")).strip() or PARTNER_REDEEM_SOURCE
    result = _redeem_code_core(
        raw_code=code,
        user_id=str(payload.get("user_id", "")),
        source=source,
        extra_log={
            "channel": "partner_api",
            "order_id": order_id,
        },
    )
    if result.get("ok"):
        callback_url = result.pop("_callback_url", "") or PARTNER_WEBHOOK_URLS.get(provided, "")
        cb_order_id = result.pop("_order_id", "") or order_id
        if callback_url:
            webhook_body = {
                "event": "redeemed",
                "code": code.strip().upper(),
                "user_id": str(payload.get("user_id", "")).strip().lower(),
                "order_id": cb_order_id,
                "redeemed_at_utc": _utc_iso(),
                "status": "redeemed",
                "channel": "partner_api",
            }
            asyncio.create_task(_dispatch_webhook(callback_url, webhook_body, cb_order_id, code))
    else:
        result.pop("_callback_url", None)
        result.pop("_order_id", None)
    if order_id:
        result["order_id"] = order_id
    result["channel"] = "partner_api"
    return result
@router.post("/partner/create-code", tags=["兑换"])
async def partner_create_code(
    payload: dict = Body(...),
    x_partner_token: str = Header(default="", alias="X-Partner-Token"),
):
    """
    第三方商城动态创建卡密（服务端对服务端）：
    - Header 鉴权（X-Partner-Token）
    - 每次商城售出一个权益，调此接口生成唯一卡密，双方同步记录
    - 可传 callback_url 指定核销后的回调地址（留空则用 PARTNER_WEBHOOK_URLS 全局配置）
    """
    if not PARTNER_REDEEM_TOKENS:
        raise HTTPException(status_code=503, detail="第三方兑换入口未启用")

    provided = str(x_partner_token or payload.get("partner_token", "")).strip()
    if provided not in PARTNER_REDEEM_TOKENS:
        raise HTTPException(status_code=401, detail="无效的 partner token")

    service_type = str(payload.get("service_type", "membership")).strip().lower()
    if service_type not in ("membership", "balance", "quota"):
        raise HTTPException(status_code=400, detail="service_type 必须是 membership / balance / quota")

    days = int(payload.get("days", 0) or 0)
    amount = int(payload.get("amount", 0) or 0)
    if service_type == "membership" and days <= 0:
        raise HTTPException(status_code=400, detail="membership 类型需传 days > 0")
    if service_type in ("balance", "quota") and amount <= 0:
        raise HTTPException(status_code=400, detail="balance/quota 类型需传 amount > 0")

    expires_at = str(payload.get("expires_at", "")).strip() or "2099-12-31T23:59:59+00:00"
    order_id = str(payload.get("order_id", "")).strip()
    description = str(payload.get("description", "")).strip()
    callback_url = str(payload.get("callback_url", "")).strip() or PARTNER_WEBHOOK_URLS.get(provided, "")

    service: dict = {"type": service_type}
    if service_type == "membership":
        service["name"] = "会员"
        service["days"] = days
        if not description:
            description = f"{days}天会员"
    elif service_type == "balance":
        service["name"] = "充值"
        service["amount"] = amount
        if not description:
            description = f"充值{amount}元"
    else:
        service["name"] = "次数"
        service["amount"] = amount
        if not description:
            description = f"增加{amount}次"

    codes = _load_redeem_codes()
    new_code = _generate_unique_code(codes, service_type)
    codes[new_code] = {
        "code": new_code,
        "status": "unused",
        "token_type": "auto",
        "expires_at": expires_at,
        "service": service,
        "description": description,
        "order_id": order_id,
        "callback_url": callback_url,
        "source": PARTNER_REDEEM_SOURCE,
        "created_by": provided,
        "created_at_utc": _utc_iso(),
    }
    _save_redeem_codes(codes)
    logger.info("第三方创建卡密 code=%s order=%s token=%s", new_code, order_id, provided[:8] + "***")
    return {
        "ok": True,
        "code": new_code,
        "order_id": order_id,
        "service": service,
        "expires_at": expires_at,
        "description": description,
    }
