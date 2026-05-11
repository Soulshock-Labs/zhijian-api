"""
core/auth.py — 权限中间件
===========================
用法：
    from core.auth import require_permission

    @router.post("/generate-weekly")
    async def generate_weekly(
        user_token: str = Form(...),
        ...
    ):
        account = require_permission(user_token, "generate")
        # account["account_id"], account["role"], account["member_no"] 等字段可用

权限表：
    generate        生成周计划 / 日教案
    observe         观察记录
    doc_space       文档空间（上传/读取）
    agent           养成 Agent
    manage_org      管理本园所（园长）
    manage_platform 管理平台（运营后台）
"""
from __future__ import annotations

from fastapi import HTTPException

from services.user_service import _verify_user_token_full

# ── 角色 → 权限集合 ──────────────────────────────────────────────────
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "guest": set(),
    "teacher": {
        "generate",
        "observe",
        "doc_space",
        "agent",
    },
    "org_admin": {
        "generate",
        "observe",
        "doc_space",
        "agent",
        "manage_org",
    },
    "platform_admin": {
        "generate",
        "observe",
        "doc_space",
        "agent",
        "manage_org",
        "manage_platform",
    },
}


def require_permission(token: str, permission: str) -> dict:
    """
    验证 token 并检查权限。
    - token 无效 → 401
    - 权限不足  → 403
    - 成功      → 返回完整 account dict
    """
    account = _verify_user_token_full(token)
    role    = account.get("role", "guest")
    allowed = ROLE_PERMISSIONS.get(role, set())

    if permission not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"权限不足（需要 {permission}，当前角色 {role}）",
        )
    return account


def get_account_optional(token: str) -> dict | None:
    """
    软验证：token 有效返回 account，无效返回 None（不抛错）。
    用于"登录后有额外功能，未登录也能用"的接口。
    """
    if not token or not token.strip():
        return None
    try:
        return _verify_user_token_full(token)
    except HTTPException:
        return None


def role_of(account: dict) -> str:
    return account.get("role", "guest")


def has_permission(account: dict, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role_of(account), set())
