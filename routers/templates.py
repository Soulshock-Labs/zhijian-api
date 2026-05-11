from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import io, os, re

from docx.opc.exceptions import PackageNotFoundError

from core.auth import require_permission
from core.settings import MAX_UPLOAD_FILE_SIZE, TEMPLATE_STANDARD_V116
from core.utils import _read_upload_with_limit
from services.data_store import _inc_template_download, _load_template_stats
from word_engine.docx_filler import _build_content_disposition
from word_engine.template_tools import (
    _build_standard_daily_template_bytes,
    _build_standard_weekly_template_bytes,
    analyze_template_docx,
    clean_template_keep_style,
)
router = APIRouter()
@router.get("/template-standard", tags=["模板中心"])
async def template_standard():
    """返回程序内置模板识别标准（与 TEMPLATE_STANDARD 配置同步）。"""
    return {
        "status": "ok",
        "standard": TEMPLATE_STANDARD_V116,
    }
@router.get("/standard-templates", tags=["模板中心"])
async def get_standard_templates():
    """返回标准模板下载信息与累计下载次数。"""
    stats = _load_template_stats()
    return {
        "status": "ok",
        "templates": [
            {
                "id": "weekly",
                "name": "标准周/活动计划模板",
                "filename": "标准周活动计划模板.docx",
                "download_count": stats.get("weekly", 0),
            },
            {
                "id": "daily",
                "name": "标准日教案模板",
                "filename": "标准日教案模板.docx",
                "download_count": stats.get("daily", 0),
            },
            {
                "id": "cleaned",
                "name": "本次模板净空版",
                "filename": "本次模板净空版.docx",
                "download_count": stats.get("cleaned", 0),
            },
        ],
    }
@router.get("/standard-template/{template_id}/download", tags=["模板中心"])
async def download_standard_template(template_id: str):
    """下载标准模板，并记录下载次数。"""
    template_id = (template_id or "").strip().lower()
    if template_id == "weekly":
        data = _build_standard_weekly_template_bytes()
        filename = "标准周活动计划模板.docx"
    elif template_id == "daily":
        data = _build_standard_daily_template_bytes()
        filename = "标准日教案模板.docx"
    else:
        raise HTTPException(status_code=404, detail="未找到该标准模板")

    _inc_template_download(template_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _build_content_disposition(filename)},
    )
@router.post("/template/clean-download", tags=["模板中心"])
async def clean_download_template(
    user_token: str = Form(..., description="登录 token"),
    template: UploadFile = File(..., description="老师上传的原始模板 .docx"),
):
    """
    基于老师上传模板生成「净空版标准模板」：
    - 仅删除教师填写/测试内容
    - 保留所有样式、间距、字体、表格结构
    """
    require_permission(user_token, "generate")
    if not (template.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 格式")
    source = await _read_upload_with_limit(template, MAX_UPLOAD_FILE_SIZE, empty_detail="上传的文件为空")

    try:
        cleaned = clean_template_keep_style(source)
    except PackageNotFoundError:
        raise HTTPException(status_code=400, detail="模板解析失败，请确认 .docx 文件有效")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板净空失败：{e}")

    _inc_template_download("cleaned")
    original = os.path.basename(template.filename or "template.docx")
    original = re.sub(r'[\\/*?:"<>|]+', "_", original)
    if original.lower().endswith(".docx"):
        original = original[:-5]
    filename = f"{original}_净空模板.docx"

    return StreamingResponse(
        io.BytesIO(cleaned),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _build_content_disposition(filename)},
    )
@router.post("/template/analyze", tags=["模板中心"])
async def template_analyze(
    user_token: str = Form(..., description="登录 token"),
    template: UploadFile = File(..., description="待自检的老师模板 .docx"),
):
    """
    上传模板，返回与 TEMPLATE_STANDARD.md v1.1 对齐的自检 JSON（启发式）。
    用于合规验证：类型猜测、关键词命中、嵌套提示、置信度说明。
    """
    require_permission(user_token, "generate")
    if not (template.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 格式")
    raw = await _read_upload_with_limit(template, MAX_UPLOAD_FILE_SIZE, empty_detail="上传的文件为空")
    try:
        return analyze_template_docx(raw)
    except PackageNotFoundError:
        raise HTTPException(status_code=400, detail="模板解析失败，请确认 .docx 文件有效")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板分析失败：{e}")
