from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import os



from core.settings import AI_MODEL, APP_ENV, DASHSCOPE_API_KEY, _BASE_DIR, _FRONTEND
router = APIRouter()
@router.get("/", tags=["前端"])
async def serve_frontend():
    """返回前端页面（同域部署时前后端共享一个 Cloud Run 服务）"""
    if os.path.exists(_FRONTEND):
        return FileResponse(_FRONTEND, media_type="text/html")
    return {
        "service": "小纸笺 API",
        "status": "running",
        "model": AI_MODEL,
        "api_key_configured": bool(DASHSCOPE_API_KEY),
    }
@router.get("/mock-token", tags=["工具"], include_in_schema=False)
async def mock_token_page():
    """第三方商城对接测试台（临时测试页）。"""
    if APP_ENV == "production":
        raise HTTPException(status_code=404, detail="测试页未开放")
    p = _BASE_DIR / "mock-mall.html"
    if p.exists():
        return FileResponse(str(p), media_type="text/html")
    raise HTTPException(status_code=404, detail="测试页未找到")
