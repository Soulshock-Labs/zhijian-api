from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import asyncio, io, json, os, re
from uuid import uuid4

from docx.opc.exceptions import PackageNotFoundError

from ai_service import _extract_template_outline, _normalize_content_payload, generate_content
from core.auth import require_permission
from core.settings import AI_MODEL, MAX_UPLOAD_FILE_SIZE, _WEEKLY_DRAFT_LOG_FILE
from core.utils import _append_jsonl, _read_upload_with_limit, _utc_iso
from services.data_store import _load_user_accounts
from services.generate_service import _build_mini_doc_payload, _generate_weekly_for_user
from word_engine.aspose_filler import _export_http_headers
from word_engine.docx_filler import (
    _build_content_disposition,
    docx_to_images_bytes,
    docx_to_pdf_bytes,
    fill_word_template,
)
from word_engine.field_map import WEEKLY_STANDARD_MODULES
from word_engine.template_tools import _build_standard_weekly_template_bytes
router = APIRouter()
@router.post("/generate", tags=["核心接口"])
async def generate(
    user_token: str = Form(..., description="登录 token"),
    theme: str = Form(..., description="教学主题"),
    phil: str = Form(..., description="教育理念"),
    activities: str = Form("[]", description="活动重点列表（JSON 数组字符串）"),
    child_initiative: bool = Form(False, description="是否有幼儿自主发起活动"),
    child_desc: str = Form("", description="幼儿自主活动描述"),
    class_level: str = Form("", description="班级类型：小班 / 中班 / 大班"),
    client: str = Form("web", description="客户端标识，mini 时返回 JSON"),
    export_format: str = Form("docx", description="导出格式：docx / pdf / png"),
    template: UploadFile = File(..., description="Word 模板文件 (.doc/.docx)"),
):
    """
    核心生成接口

    - **theme**：教学主题，如「春天来了」
    - **phil**：教育理念，如「蒙氏教育（AMI/AMS）」
    - **activities**：活动重点，如 `["outdoor","area","morning"]`
    - **child_initiative**：是否有幼儿自主发起活动
    - **child_desc**：自主活动描述
    - **class_level**：班级类型（小班/中班/大班），影响活动难度与目标表述
    - **template**：用户上传的 Word 模板文件

    默认返回填充好的 `.docx` 文件流；
    当 `client=mini` 时，返回包含 `file_base64` 的 JSON，便于小程序直接写本地文件。
    """
    require_permission(user_token, "generate")

    # ── 校验文件格式 ──
    if not template.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="仅支持 .docx 格式的 Word 文件",
        )

    # ── 解析活动列表 ──
    try:
        acts_list: list[str] = json.loads(activities)
    except (json.JSONDecodeError, TypeError):
        acts_list = []
    if not isinstance(acts_list, list):
        acts_list = []

    # ── 读取模板二进制 ──
    template_bytes = await _read_upload_with_limit(template, MAX_UPLOAD_FILE_SIZE)
    _append_jsonl(_WEEKLY_DRAFT_LOG_FILE, {
        "ts": _utc_iso(),
        "event": "template_submit",
        "flow": "custom_template_generate",
        "template_filename": os.path.basename(template.filename or "template.docx"),
        "theme": theme,
        "phil": phil,
        "activities": acts_list,
        "child_initiative": bool(child_initiative),
    })

    # ── 调用 AI 生成内容 ──
    template_outline = _extract_template_outline(template_bytes)
    ai_content = generate_content(
        theme=theme,
        phil=phil,
        activities=acts_list,
        child_initiative=child_initiative,
        child_desc=child_desc,
        template_outline=template_outline,
        class_level=class_level.strip(),
    )

    # ── 铁律填充 ──
    try:
        filled_bytes, export_engine = fill_word_template(
            template_bytes=template_bytes,
            theme=theme,
            phil=phil,
            ai_content=ai_content,
            activities=acts_list,
            child_initiative=child_initiative,
            child_desc=child_desc,
            class_level=class_level.strip(),
        )
    except PackageNotFoundError:
        raise HTTPException(status_code=400, detail="模板解析失败，请确认上传的是有效 .docx 文件")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模板填充失败：{e}")

    # ── 导出文件名 + 格式转换 ──
    original_name = os.path.basename(template.filename or "template.docx")
    original_name = re.sub(r'[\\/*?:"<>|]+', "_", original_name)
    if original_name.lower().endswith(".docx"):
        original_name = original_name[:-5]

    export_fmt = export_format.strip().lower()

    # 小程序返回 JSON
    if client.strip().lower() == "mini":
        return _build_mini_doc_payload(
            filled_bytes=filled_bytes,
            original_name=f"{original_name}.docx",
            export_engine=export_engine,
        )

    # 导出格式选择
    if export_fmt == "pdf":
        try:
            output_bytes = docx_to_pdf_bytes(filled_bytes)
            filename = f"{original_name}.pdf"
            media_type = "application/pdf"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF 生成失败：{e}")
    elif export_fmt == "png":
        try:
            images_bytes = docx_to_images_bytes(filled_bytes, format="png")
            if not images_bytes:
                raise ValueError("无法转换图片")
            # 多页则返回第一页，或在响应中打包所有页面
            # 简化版：返回第一页
            output_bytes = images_bytes[0]
            filename = f"{original_name}_page1.png"
            media_type = "image/png"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"图片导出失败：{e}")
    else:  # docx（默认）
        output_bytes = filled_bytes
        filename = f"{original_name}.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    h = {
        "Content-Disposition": _build_content_disposition(filename),
        "X-AI-Model": AI_MODEL,
    }
    h.update(_export_http_headers(export_engine))
    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type=media_type,
        headers=h,
    )
@router.post("/preview", tags=["调试"])
async def preview(
    user_token: str = Form(...),
    theme: str = Form(...),
    phil: str = Form(...),
    activities: str = Form("[]"),
    child_initiative: bool = Form(False),
    child_desc: str = Form(""),
    class_level: str = Form("", description="班级类型：小班 / 中班 / 大班"),
):
    """返回 AI 生成的结构化内容 JSON，用于前端预览和调试（无需上传文件）"""
    require_permission(user_token, "generate")
    acts_list: list[str] = json.loads(activities) if activities else []
    content = generate_content(theme, phil, acts_list, child_initiative, child_desc, class_level=class_level.strip())
    return {"status": "ok", "theme": theme, "philosophy": phil, "content": content}
@router.post("/standard-weekly-draft", tags=["标准周模板"])
async def standard_weekly_draft(
    user_token: str = Form(...),
    theme: str = Form(...),
    phil: str = Form(...),
    activities: str = Form("[]"),
    child_initiative: bool = Form(False),
    child_desc: str = Form(""),
    class_level: str = Form("", description="班级类型：小班 / 中班 / 大班"),
):
    """生成标准周模板草稿（JSON，可在前端修改后再导出）。"""
    require_permission(user_token, "generate")
    try:
        acts_list: list[str] = json.loads(activities) if activities else []
    except Exception:
        acts_list = []
    if not isinstance(acts_list, list):
        acts_list = []
    content = generate_content(theme, phil, acts_list, child_initiative, child_desc, class_level=class_level.strip())
    draft_id = f"wd_{uuid4().hex[:10]}"
    _append_jsonl(_WEEKLY_DRAFT_LOG_FILE, {
        "ts": _utc_iso(),
        "event": "standard_weekly_draft",
        "draft_id": draft_id,
        "theme": theme,
        "phil": phil,
        "activities": acts_list,
        "child_initiative": bool(child_initiative),
    })
    return {
        "status": "ok",
        "draft_id": draft_id,
        "schema_version": "weekly-standard-v1.0",
        "module_catalog": WEEKLY_STANDARD_MODULES,
        "draft": {
            "theme": theme,
            "phil": phil,
            "activities": acts_list,
            "child_initiative": bool(child_initiative),
            "child_desc": child_desc or "",
            "content": content,
        },
    }
@router.post("/standard-weekly-export", tags=["标准周模板"])
async def standard_weekly_export(
    user_token: str = Form(..., description="登录 token"),
    draft_json: str = Form(..., description="前端可编辑草稿 JSON"),
):
    """按可编辑草稿导出标准周模板 Word。"""
    require_permission(user_token, "generate")
    try:
        payload = json.loads(draft_json)
        if not isinstance(payload, dict):
            raise ValueError("draft_json 必须是对象")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"draft_json 解析失败：{e}")

    theme = str(payload.get("theme") or "").strip()
    phil = str(payload.get("phil") or "五大领域").strip()
    child_desc = str(payload.get("child_desc") or "").strip()
    child_initiative = bool(payload.get("child_initiative", False))
    acts_list = payload.get("activities", [])
    if not isinstance(acts_list, list):
        acts_list = []
    raw_content = payload.get("content", {})
    if not theme:
        raise HTTPException(status_code=400, detail="草稿缺少主题（theme）")

    content = _normalize_content_payload(
        raw_content if isinstance(raw_content, dict) else {},
        theme=theme,
        phil=phil,
        activities=acts_list,
        child_initiative=child_initiative,
        child_desc=child_desc,
    )
    template_bytes = _build_standard_weekly_template_bytes()
    try:
        filled_bytes, export_engine = fill_word_template(
            template_bytes=template_bytes,
            theme=theme,
            phil=phil,
            ai_content=content,
            activities=acts_list,
            child_initiative=child_initiative,
            child_desc=child_desc,
            fill_unselected=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标准模板导出失败：{e}")

    draft_id = str(payload.get("draft_id") or "")
    _append_jsonl(_WEEKLY_DRAFT_LOG_FILE, {
        "ts": _utc_iso(),
        "event": "standard_weekly_export",
        "draft_id": draft_id or f"wd_{uuid4().hex[:8]}",
        "theme": theme,
        "phil": phil,
        "activities": acts_list,
    })

    safe_theme = re.sub(r'[\\/*?:"<>|]+', "_", theme)
    filename = f"标准周模板_{safe_theme}.docx"
    h = {
        "Content-Disposition": _build_content_disposition(filename),
        "X-AI-Model": AI_MODEL,
    }
    h.update(_export_http_headers(export_engine))
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=h,
    )
@router.post("/batch/generate-weekly", tags=["批量速写"])
async def batch_generate_weekly(payload: dict = Body(...)):
    """
    批量速写接口：同时为多位老师生成个性化周计划。

    每位老师自动使用自己的 agent_profile（性格/风格），asyncio 并发执行。

    请求体：
    {
      "openids": ["openid_1", "openid_2"],   # 目标老师列表
      "theme": "春天来了",
      "phil": "以幼儿为中心",
      "activities": ["户外活动", "区域活动"],
      "class_level": "中班",
      "admin_token": "..."                   # 管理员 token（可选鉴权）
    }
    """
    account = require_permission(str(payload.get("user_token", "")).strip(), "manage_platform")
    openids: list[str] = payload.get("openids", [])
    theme = str(payload.get("theme", "")).strip()
    phil = str(payload.get("phil", "以幼儿为中心")).strip()
    activities = payload.get("activities", ["户外活动", "区域活动"])
    class_level = str(payload.get("class_level", "中班")).strip()

    if not openids:
        raise HTTPException(status_code=400, detail="openids 不能为空")
    if not theme:
        raise HTTPException(status_code=400, detail="theme 不能为空")
    if len(openids) > 50:
        raise HTTPException(status_code=400, detail="单次最多 50 位老师")

    semaphore = asyncio.Semaphore(5)

    async def limited_generate(openid: str):
        async with semaphore:
            return await _generate_weekly_for_user(openid, theme, phil, activities, class_level)

    tasks = [limited_generate(openid) for openid in openids]
    results = await asyncio.gather(*tasks)

    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count

    return {
        "status": "ok",
        "total": len(openids),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "viewer_member_no": str(account.get("member_no", "")).strip(),
        "results": list(results),
    }
@router.get("/batch/users", tags=["批量速写"])
async def batch_list_users(user_token: str, offset: int = 0, limit: int = 100):
    """列出所有注册用户（openid + agent_profile），用于批量速写前选择目标。"""
    require_permission(user_token, "manage_platform")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 不能小于 0")
    if limit <= 0 or limit > 200:
        raise HTTPException(status_code=400, detail="limit 必须在 1-200 之间")
    accounts = _load_user_accounts()
    users = []
    for openid, entry in accounts.items():
        users.append({
            "openid": openid,
            "user_id": entry.get("user_id") or "",
            "agent": entry.get("agent_profile", {}),
            "created_at": entry.get("created_at", ""),
        })
    users.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    page = users[offset: offset + limit]
    return {"status": "ok", "count": len(users), "offset": offset, "limit": limit, "users": page}
