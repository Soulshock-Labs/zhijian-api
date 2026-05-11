from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile

import bcrypt
import hashlib
from datetime import datetime, timezone

from core.auth import ROLE_PERMISSIONS, require_permission
from core.settings import APP_ENV
from core.utils import _parse_iso_datetime, _utc_iso
from services.data_store import _load_redeem_codes, _load_user_accounts, _load_user_services, _save_user_accounts, _save_user_services, _load_account_index, _save_account_index
from services.user_service import (
    _create_account,
    _get_account_by_member_no,
    _get_account_by_phone,
    _get_or_create_user,
    _issue_token,
    _verify_user_token,
    _verify_user_token_full,
)

router = APIRouter()
REGISTER_ROLES = {"guest", "teacher", "org_admin"}


def _extract_token(request: Request, query_token: str = "") -> str:
    """从 Authorization: Bearer <token> 或 query param 中提取 user_token。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return query_token.strip()


def _hash_password(password: str) -> str:
    """使用 bcrypt 存储密码。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _is_legacy_sha256(password_hash: str) -> bool:
    value = str(password_hash or "").strip().lower()
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _verify_password(password: str, password_hash: str) -> bool:
    stored = str(password_hash or "").strip()
    if not stored:
        return False
    if _is_legacy_sha256(stored):
        return stored == hashlib.sha256(password.encode("utf-8")).hexdigest()
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except ValueError:
        return False


def _build_service_info(account_id: str) -> dict:
    """读取用户权益状态（按 account_id 查询）。"""
    user_services = _load_user_services()
    entry = user_services.get(account_id, {})
    membership_until = entry.get("membership_until")
    is_active_member = False
    if membership_until:
        try:
            until_dt = datetime.fromisoformat(str(membership_until))
            is_active_member = datetime.now(timezone.utc) < until_dt
        except Exception:
            pass
    return {
        "membership_until": membership_until,
        "is_active_member": is_active_member,
        "balance": int(entry.get("balance", 0) or 0),
        "quota":   int(entry.get("quota",   0) or 0),
    }


def _account_response(account: dict, token: str, is_new: bool = False) -> dict:
    """统一的账号响应格式。"""
    return {
        "ok":          True,
        "is_new":      is_new,
        "account_id":  account["account_id"],
        "member_no":   account.get("member_no", ""),
        "user_id":     account["account_id"],      # 向后兼容旧字段
        "user_token":  token,
        "role":        account.get("role", "teacher"),
        "org_id":      account.get("org_id", ""),
        "agent_profile": account.get("agent_profile", {}),
        "service":     _build_service_info(account["account_id"]),
    }


def _member_no_int(account: dict) -> int | None:
    try:
        return int(str(account.get("member_no", "")).strip())
    except Exception:
        return None


# ── /user/wxlogin ─────────────────────────────────────────────────────
@router.post("/user/wxlogin", tags=["用户"])
async def user_wxlogin(
    code: str = Form(..., description="微信 wx.login() 返回的 code"),
):
    """
    小程序登录：code → openid → 查/建账号 → 返回 token。
    如果 openid 未绑定手机号，返回 bound=False，前端引导绑定。
    """
    import httpx
    import os

    appid  = os.getenv("WECHAT_APPID", "")
    secret = os.getenv("WECHAT_SECRET", "")

    if appid and secret:
        try:
            url = (
                f"https://api.weixin.qq.com/sns/jscode2session"
                f"?appid={appid}&secret={secret}&js_code={code}&grant_type=authorization_code"
            )
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                wx_data = resp.json()
            openid = str(wx_data.get("openid", "")).strip()
            if not openid:
                raise HTTPException(status_code=400, detail=f"微信登录失败：{wx_data.get('errmsg', '未知')}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"微信接口调用失败：{e}")
    else:
        if APP_ENV == "production":
            raise HTTPException(status_code=500, detail="微信登录配置缺失")
        openid = f"dev_{code[:16]}"

    account = _get_or_create_user(openid)
    token   = _issue_token(account["account_id"])

    # 重新读取最新 account（_issue_token 已写回）
    accounts = _load_user_accounts()
    account  = accounts.get(account["account_id"], account)

    return {
        **_account_response(account, token),
        "openid":      openid,
        "phone_bound": bool(account.get("phone")),   # 前端判断是否需要绑定手机号
    }


# ── /user/register ────────────────────────────────────────────────────
@router.post("/user/register", tags=["用户"])
async def user_register(payload: dict = Body(...)):
    """
    注册：只需密码，系统自动分配会员号（如 10000）。
    会员号即用户名，用于后续登录。
    测试时可传 member_no 手动指定（4位测试号）。
    """
    password  = str(payload.get("password", "")).strip()
    member_no = str(payload.get("member_no", "")).strip()  # 可选，测试用
    role      = str(payload.get("role", "teacher")).strip().lower() or "teacher"

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")
    if role not in REGISTER_ROLES:
        raise HTTPException(status_code=400, detail="角色无效，请选择幼师、园长或游客")

    account = _create_account(_hash_password(password), member_no=member_no, role=role)
    token   = _issue_token(account["account_id"])

    return _account_response(account, token, is_new=True)


# ── /user/login ───────────────────────────────────────────────────────
@router.post("/user/login", tags=["用户"])
async def user_login(payload: dict = Body(...)):
    """
    登录：会员号 + 密码。
    会员号即注册时系统分配的数字 ID（如 10000）。
    """
    member_no = str(payload.get("member_no", "") or payload.get("user_id", "")).strip()
    password  = str(payload.get("password", "")).strip()

    if not member_no or not password:
        raise HTTPException(status_code=400, detail="请填写会员号和密码")

    account = _get_account_by_member_no(member_no)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在，请先注册")

    stored_hash = account.get("password_hash", "")
    if not stored_hash:
        raise HTTPException(status_code=400, detail="该账号未设置密码，请联系管理员")
    if not _verify_password(password, stored_hash):
        raise HTTPException(status_code=401, detail="密码错误")

    if _is_legacy_sha256(stored_hash):
        accounts = _load_user_accounts()
        if account["account_id"] in accounts:
            accounts[account["account_id"]]["password_hash"] = _hash_password(password)
            accounts[account["account_id"]]["updated_at_utc"] = _utc_iso()
            _save_user_accounts(accounts)

    token = _issue_token(account["account_id"])

    accounts = _load_user_accounts()
    account  = accounts.get(account["account_id"], account)

    return _account_response(account, token)


# ── /user/agent ───────────────────────────────────────────────────────
@router.post("/user/agent", tags=["用户"])
async def update_agent_profile(
    user_token:  str = Form(..., description="登录 token"),
    name:        str = Form("小助手",   description="智能体名字"),
    personality: str = Form("热心、耐心", description="性格特征"),
    tone:        str = Form("亲切温暖", description="说话音调"),
    style:       str = Form("鼓励式教学", description="教学风格"),
):
    """自定义用户的 AI 智能体性格，影响所有生成内容的风格。需要 agent 权限。"""
    from core.auth import require_permission
    account = require_permission(user_token, "agent")

    accounts = _load_user_accounts()
    aid      = account["account_id"]
    accounts[aid]["agent_profile"] = {
        "name":        name,
        "personality": personality,
        "tone":        tone,
        "style":       style,
    }
    _save_user_accounts(accounts)
    return {"ok": True, "agent_profile": accounts[aid]["agent_profile"]}


# ── /user/me ──────────────────────────────────────────────────────────
@router.get("/user/me", tags=["用户"])
async def get_me(user_token: str):
    """获取当前登录用户信息。"""
    account = _verify_user_token_full(user_token)
    return _account_response(account, user_token)


# ── /user/internal-beta/accounts ─────────────────────────────────────
@router.get("/user/internal-beta/accounts", tags=["用户"])
async def list_internal_beta_accounts(request: Request, user_token: str = "", offset: int = 0, limit: int = 200):
    """
    返回内测账号列表。
    - 仅 platform_admin 可访问
    - member_no=1001 时，默认只返回另外 99 个（1002-1100）
    - 其他平台管理员可返回整组内测账号
    """
    account = require_permission(_extract_token(request, user_token), "manage_platform")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 不能小于 0")
    if limit <= 0 or limit > 200:
        raise HTTPException(status_code=400, detail="limit 必须在 1-200 之间")
    accounts = _load_user_accounts()

    def _as_int(value: str) -> int | None:
        try:
            return int(str(value).strip())
        except Exception:
            return None

    caller_member_no = str(account.get("member_no", "")).strip()
    rows: list[dict] = []
    for entry in accounts.values():
        if not isinstance(entry, dict):
            continue
        member_no = str(entry.get("member_no", "")).strip()
        member_no_int = _as_int(member_no)
        if member_no_int is None:
            continue
        if 1001 <= member_no_int <= 1100:
            if caller_member_no == "1001" and member_no == "1001":
                continue
            rows.append({
                "account_id": entry.get("account_id", ""),
                "member_no": member_no,
                "role": entry.get("role", "teacher"),
                "org_id": entry.get("org_id", ""),
                "created_at_utc": entry.get("created_at_utc", ""),
                "updated_at_utc": entry.get("updated_at_utc", ""),
            })

    rows.sort(key=lambda item: int(item["member_no"]))
    page = rows[offset: offset + limit]
    return {
        "ok": True,
        "viewer_member_no": caller_member_no,
        "count": len(rows),
        "offset": offset,
        "limit": limit,
        "accounts": page,
    }


@router.get("/user/internal-beta/redeem-codes", tags=["用户"])
async def list_internal_beta_redeem_codes(request: Request, user_token: str = ""):
    """
    返回内测兑换码使用情况。
    仅 1001 / 10001 可访问。
    """
    account = require_permission(_extract_token(request, user_token), "manage_platform")
    caller_member_no = str(account.get("member_no", "")).strip()
    if caller_member_no not in {"1001", "10001"}:
        raise HTTPException(status_code=403, detail="仅指定内测管理员可查看兑换码使用情况")

    codes = _load_redeem_codes()
    items: list[dict] = []
    used = 0
    unused = 0
    expired = 0
    for code, item in codes.items():
        status = str(item.get("status", "unused")).strip().lower() or "unused"
        expires_at = str(item.get("expires_at", "")).strip()
        expire_dt = _parse_iso_datetime(expires_at)
        if status == "used":
          used += 1
        elif expire_dt is not None and datetime.now(timezone.utc) > expire_dt:
          expired += 1
        else:
          unused += 1

        items.append({
            "code": code,
            "status": status,
            "token_type": item.get("token_type", ""),
            "description": item.get("description", ""),
            "service": item.get("service", {}),
            "expires_at": expires_at,
            "used_by": item.get("used_by", ""),
            "used_at_utc": item.get("used_at_utc", ""),
            "batch": item.get("batch", ""),
        })

    items.sort(key=lambda row: row["code"])
    return {
        "ok": True,
        "count": len(items),
        "summary": {
            "unused": unused,
            "used": used,
            "expired": expired,
        },
        "codes": items,
    }


@router.get("/user/admin/users", tags=["用户"])
async def admin_list_users(request: Request, user_token: str = "", offset: int = 0, limit: int = 500):
    """
    全量用户后台列表。
    仅 10001 可访问，用于审核授权。
    """
    account = require_permission(_extract_token(request, user_token), "manage_platform")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 不能小于 0")
    if limit <= 0 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1-500 之间")
    caller_member_no = str(account.get("member_no", "")).strip()
    if caller_member_no != "10001":
        raise HTTPException(status_code=403, detail="仅主账号 10001 可查看全量用户信息")

    accounts = _load_user_accounts()
    user_services = _load_user_services()
    rows: list[dict] = []
    for entry in accounts.values():
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role", "guest")).strip() or "guest"
        aid = str(entry.get("account_id", "")).strip()
        service = user_services.get(aid, {})
        rows.append({
            "account_id": aid,
            "member_no": entry.get("member_no", ""),
            "role": role,
            "permissions": sorted(ROLE_PERMISSIONS.get(role, set())),
            "org_id": entry.get("org_id", ""),
            "note": entry.get("note", ""),
            "phone": entry.get("phone", ""),
            "openid": entry.get("openid", ""),
            "created_at_utc": entry.get("created_at_utc", ""),
            "updated_at_utc": entry.get("updated_at_utc", ""),
            "service": {
                "membership_until": service.get("membership_until"),
                "balance": int(service.get("balance", 0) or 0),
                "quota": int(service.get("quota", 0) or 0),
            },
        })

    rows.sort(key=lambda item: (_member_no_int(item) is None, _member_no_int(item) or 0))
    page = rows[offset: offset + limit]
    return {"ok": True, "count": len(rows), "offset": offset, "limit": limit, "users": page}


@router.post("/user/admin/authorize", tags=["用户"])
async def admin_authorize_user(payload: dict = Body(...)):
    """
    主账号 10001 审核授权：
    - 调整角色
    - 调整 org_id
    - 写备注
    - 可选设置会员有效期
    """
    user_token = str(payload.get("user_token", "")).strip()
    account = require_permission(user_token, "manage_platform")
    caller_member_no = str(account.get("member_no", "")).strip()
    if caller_member_no != "10001":
        raise HTTPException(status_code=403, detail="仅主账号 10001 可审核授权")

    target_member_no = str(payload.get("member_no", "")).strip()
    target_account_id = str(payload.get("account_id", "")).strip()

    # 用 sentinel 区分"未传"和"传了空字符串（表示清空）"
    UNSET = object()
    def _field(key):
        return payload[key] if key in payload else UNSET

    role             = _field("role")
    org_id           = _field("org_id")
    note             = _field("note")
    membership_until = _field("membership_until")

    if role is not UNSET:
        role = str(role or "").strip().lower()
        if role and role not in {"guest", "teacher", "org_admin", "platform_admin"}:
            raise HTTPException(status_code=400, detail="角色无效")

    accounts = _load_user_accounts()
    target: dict | None = None
    target_key = ""
    for aid, entry in accounts.items():
        if not isinstance(entry, dict):
            continue
        if target_account_id and aid == target_account_id:
            target = entry
            target_key = aid
            break
        if target_member_no and str(entry.get("member_no", "")).strip() == target_member_no:
            target = entry
            target_key = aid
            break

    if not target or not target_key:
        raise HTTPException(status_code=404, detail="目标账号不存在")

    # 传了就更新（空字符串 = 清空）
    if role is not UNSET:
        target["role"] = role or target.get("role", "guest")  # role 不允许清空为空串
    if org_id is not UNSET:
        target["org_id"] = str(org_id or "").strip()
    if note is not UNSET:
        target["note"] = str(note or "").strip()
    target["updated_at_utc"] = _utc_iso()
    accounts[target_key] = target
    _save_user_accounts(accounts)

    final_membership_until = None
    if membership_until is not UNSET:
        user_services = _load_user_services()
        svc = user_services.get(target_key, {"membership_until": None, "balance": 0, "quota": 0, "rewards": []})
        val = str(membership_until or "").strip()
        svc["membership_until"] = val or None   # 空字符串 = 清空会员
        user_services[target_key] = svc
        _save_user_services(user_services)
        final_membership_until = svc["membership_until"]

    return {
        "ok": True,
        "account_id": target_key,
        "member_no": target.get("member_no", ""),
        "role": target.get("role", "guest"),
        "org_id": target.get("org_id", ""),
        "note": target.get("note", ""),
        "membership_until": final_membership_until,
    }


# ── /user/admin/reset-password ────────────────────────────────────────
@router.post("/user/admin/reset-password", tags=["用户"])
async def admin_reset_password(payload: dict = Body(...)):
    """
    主账号 10001 重置任意账号密码（含自己）。
    payload: { user_token, member_no, new_password }
    """
    user_token = str(payload.get("user_token", "")).strip()
    account = require_permission(user_token, "manage_platform")
    caller_member_no = str(account.get("member_no", "")).strip()
    if caller_member_no != "10001":
        raise HTTPException(status_code=403, detail="仅主账号 10001 可重置密码")

    target_member_no = str(payload.get("member_no", "")).strip()
    new_password = str(payload.get("new_password", "")).strip()
    if not target_member_no or not new_password:
        raise HTTPException(status_code=400, detail="member_no 和 new_password 不能为空")

    accounts = _load_user_accounts()
    target_key = None
    for aid, entry in accounts.items():
        if isinstance(entry, dict) and str(entry.get("member_no", "")).strip() == target_member_no:
            target_key = aid
            break

    if not target_key:
        raise HTTPException(status_code=404, detail="账号不存在")

    accounts[target_key]["password_hash"] = _hash_password(new_password)
    accounts[target_key]["updated_at_utc"] = _utc_iso()
    _save_user_accounts(accounts)

    return {"ok": True, "member_no": target_member_no, "msg": "密码已重置"}


# ── /user/admin/reset-phone ───────────────────────────────────────────
@router.post("/user/admin/reset-phone", tags=["用户"])
async def admin_reset_phone(payload: dict = Body(...)):
    """
    主账号 10001 修改任意账号手机号（含自己）。
    payload: { user_token, member_no, new_phone }
    """
    user_token = str(payload.get("user_token", "")).strip()
    account = require_permission(user_token, "manage_platform")
    caller_member_no = str(account.get("member_no", "")).strip()
    if caller_member_no != "10001":
        raise HTTPException(status_code=403, detail="仅主账号 10001 可修改手机号")

    target_member_no = str(payload.get("member_no", "")).strip()
    new_phone = str(payload.get("new_phone", "")).strip()
    if not target_member_no or not new_phone:
        raise HTTPException(status_code=400, detail="member_no 和 new_phone 不能为空")

    accounts = _load_user_accounts()
    index = _load_account_index()

    target_key = None
    old_phone = ""
    for aid, entry in accounts.items():
        if isinstance(entry, dict) and str(entry.get("member_no", "")).strip() == target_member_no:
            target_key = aid
            old_phone = str(entry.get("phone", "")).strip()
            break

    if not target_key:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 更新 index：删旧 phone 键，加新 phone 键
    old_key = f"phone:{old_phone}"
    new_key = f"phone:{new_phone}"
    if old_key in index:
        del index[old_key]
    index[new_key] = target_key

    accounts[target_key]["phone"] = new_phone
    accounts[target_key]["user_id"] = new_phone
    accounts[target_key]["updated_at_utc"] = _utc_iso()
    _save_user_accounts(accounts)
    _save_account_index(index)

    return {"ok": True, "member_no": target_member_no, "phone": new_phone, "msg": "手机号已更新"}

