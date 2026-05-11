from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import datetime, json, uuid
from uuid import uuid4

from core.settings import _FEEDBACK_LOG_FILE, _REGISTER_LOG_FILE
from core.state import logger
from core.utils import _append_jsonl, _utc_iso
from services.data_store import _inc_app_stat, _load_app_stats, _load_registered_ids
from services.data_store import _save_app_stats
router = APIRouter()
@router.get("/public-stats", tags=["运营"])
async def public_stats():
    """首页公开统计：内测体验点击量、模块点击量、注册人数、建议留言数。"""
    stats = _load_app_stats()
    return {
        "status": "ok",
        "stats": {
            "home_visits": int(stats.get("home_visits", 0)),
            "module_clicks": int(stats.get("module_clicks", 0)),
            "register_count": int(stats.get("register_count", 0)),
            "feedback_count": int(stats.get("feedback_count", 0)),
        },
    }
@router.post("/track-event", tags=["运营"])
async def track_event(payload: dict = Body(...)):
    """
    轻量埋点：用于首页访问与模块点击计数。
    支持 event: home_visit | module_click | register
    """
    event = str(payload.get("event", "")).strip().lower()
    if event == "home_visit":
        stats = _inc_app_stat("home_visits", 1)
    elif event == "module_click":
        stats = _inc_app_stat("module_clicks", 1)
    elif event == "register":
        stats = _inc_app_stat("register_count", 1)
    else:
        raise HTTPException(status_code=400, detail="unsupported event")
    return {"ok": True, "stats": stats}
@router.post("/register-lite", tags=["运营"])
async def register_lite(payload: dict = Body(...)):
    """轻量内测注册（按联系方式去重计数）。"""
    identifier = str(payload.get("identifier", "")).strip().lower()
    role = str(payload.get("role", "")).strip().lower()
    if len(identifier) < 3:
        raise HTTPException(status_code=400, detail="请填写有效联系方式")
    if role not in {"teacher", "manager"}:
        raise HTTPException(status_code=400, detail="请先选择职业身份（老师/管理者）")

    existed = _load_registered_ids()
    is_new = identifier not in existed
    row = {
        "id": f"RG-{uuid4().hex[:10]}",
        "created_at_utc": _utc_iso(),
        "identifier": identifier[:160],
        "nickname": str(payload.get("nickname", "")).strip()[:80],
        "role": role,
        "kindergarten": str(payload.get("kindergarten", "")).strip()[:160],
        "page_url": str(payload.get("page_url", "")).strip()[:800],
    }
    _append_jsonl(_REGISTER_LOG_FILE, row)

    stats = _load_app_stats()
    if is_new:
        stats["register_count"] = int(stats.get("register_count", 0)) + 1
        _save_app_stats(stats)
    return {
        "ok": True,
        "registered": True,
        "is_new": bool(is_new),
        "register_count": int(_load_app_stats().get("register_count", 0)),
    }
@router.post("/feedback", tags=["运营"])
async def submit_feedback(payload: dict = Body(...)):
    """
    内测意见留言：前端提交建议后写入 jsonl 日志，并累计反馈数量。
    """
    from datetime import datetime
    import uuid

    message = str(payload.get("message", "")).strip()
    role = str(payload.get("role", "")).strip().lower()
    if role not in {"teacher", "manager"}:
        raise HTTPException(status_code=400, detail="请先选择职业身份（老师/管理者）")
    if len(message) < 2:
        raise HTTPException(status_code=400, detail="建议内容至少 2 个字")

    fb_id = f"FB-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    row = {
        "id": fb_id,
        "created_at_utc": datetime.utcnow().isoformat() + "Z",
        "nickname": str(payload.get("nickname", "")).strip()[:80],
        "contact": str(payload.get("contact", "")).strip()[:160],
        "role": role,
        "kindergarten": str(payload.get("kindergarten", "")).strip()[:160],
        "message": message[:3000],
        "page_url": str(payload.get("page_url", "")).strip()[:800],
        "module": str(payload.get("module", "")).strip()[:40],
        "user_agent": str(payload.get("user_agent", "")).strip()[:400],
    }
    try:
        with _FEEDBACK_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("写入反馈日志失败：%s", e)

    stats = _inc_app_stat("feedback_count", 1)
    logger.info("USER_FEEDBACK %s", json.dumps(row, ensure_ascii=False))
    return {
        "ok": True,
        "feedback_id": fb_id,
        "feedback_count": int(stats.get("feedback_count", 0)),
    }
@router.get("/feedback-feed", tags=["运营"])
async def feedback_feed(limit: int = 30):
    """
    留言墙数据：默认匿名显示昵称，前端可点击“显示昵称”再展开。
    """
    safe_limit = max(1, min(int(limit or 30), 100))
    rows: list[dict] = []
    if _FEEDBACK_LOG_FILE.exists():
        try:
            lines = _FEEDBACK_LOG_FILE.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-300:]):
                if len(rows) >= safe_limit:
                    break
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except Exception:
                    continue
                nickname = str(raw.get("nickname", "")).strip()
                rows.append({
                    "id": str(raw.get("id", "")),
                    "created_at_utc": str(raw.get("created_at_utc", "")),
                    "role": str(raw.get("role", "")).strip().lower(),
                    "kindergarten": str(raw.get("kindergarten", "")).strip(),
                    "message": str(raw.get("message", "")).strip()[:500],
                    "nickname": nickname[:80],
                    "nickname_masked": "匿名用户",
                    "has_nickname": bool(nickname),
                })
        except Exception as e:
            logger.warning("读取反馈论坛失败：%s", e)
    return {"status": "ok", "items": rows}
