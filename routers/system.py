from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import datetime, json, uuid

from core.settings import AI_MODEL, APP_VERSION, DASHSCOPE_API_KEY
from core.state import aw, logger
from services.data_store import _knowledge_base_status
router = APIRouter()
@router.get("/health", tags=["健康检查"])
async def health():
    """Cloud Run / 负载均衡健康探针专用"""
    knowledge_base = _knowledge_base_status()
    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "model": AI_MODEL,
        "api_key_configured": bool(DASHSCOPE_API_KEY),
        "api_key_note": "api_key_configured 仅表示已设置 DASHSCOPE_API_KEY，未校验密钥是否有效",
        "aspose_available": aw is not None,
        "export_note": (
            "/generate 与 /generate-daily 优先 Aspose，失败则回退 python-docx；"
            "响应头 X-Export-Engine 为本次实际使用的引擎"
        ),
        "knowledge_base": knowledge_base,
    }
@router.get("/knowledge-base/status", tags=["调试"])
async def knowledge_base_status():
    return {
        "status": "ok",
        "knowledge_base": _knowledge_base_status(),
    }
@router.post("/bug-report", tags=["调试"])
async def submit_bug_report(payload: dict = Body(...)):
    """
    前端导出失败上报入口：将上下文写入服务日志并返回 report_id。
    """
    from datetime import datetime
    import uuid

    report_id = f"BR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    safe = {
        "report_id": report_id,
        "created_at_utc": datetime.utcnow().isoformat() + "Z",
        "api_base": str(payload.get("api_base", ""))[:300],
        "page_url": str(payload.get("page_url", ""))[:800],
        "endpoint": str(payload.get("endpoint", ""))[:120],
        "error_message": str(payload.get("error_message", ""))[:2000],
        "theme": str(payload.get("theme", ""))[:200],
        "phil": str(payload.get("phil", ""))[:120],
        "file_name": str(payload.get("file_name", ""))[:240],
        "activities": payload.get("activities", []),
        "user_agent": str(payload.get("user_agent", ""))[:400],
        "app_version_front": str(payload.get("app_version_front", ""))[:40],
    }
    logger.error("EXPORT_BUG_REPORT %s", json.dumps(safe, ensure_ascii=False))
    return {"ok": True, "report_id": report_id}
