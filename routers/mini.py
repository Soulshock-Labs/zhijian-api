from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import json, os, re, tempfile
from pathlib import Path
from uuid import uuid4

from docx.opc.exceptions import PackageNotFoundError

from ai_service import _extract_template_outline, generate_content
from core.auth import require_permission
from core.settings import MAX_UPLOAD_FILE_SIZE, OPENAI_API_KEY, VOICE_TRANSCRIBE_MODEL, _TEMP_TEMPLATE_DIR
from core.settings import _WEEKLY_DRAFT_LOG_FILE
from core.state import _TEMP_EXPORTS, _TEMP_TEMPLATES, voice_client
from core.utils import _append_jsonl, _read_upload_with_limit, _utc_iso
from services.generate_service import _build_mini_doc_payload
from word_engine.aspose_filler import _export_http_headers
from word_engine.docx_filler import _build_content_disposition, fill_word_template
router = APIRouter()
@router.post("/generate-mini", tags=["核心接口"])
async def generate_mini(
    user_token: str = Form(..., description="登录 token"),
    theme: str = Form(..., description="教学主题"),
    template: UploadFile = File(..., description="Word 模板文件 (.doc/.docx)"),
    phil: str = Form("五大领域", description="教育理念"),
    activities: str = Form("[]", description="活动重点列表（JSON 数组字符串）"),
    child_initiative: bool = Form(False, description="是否有幼儿自主发起活动"),
    child_desc: str = Form("", description="幼儿自主活动描述"),
    class_level: str = Form("", description="班级类型：小班 / 中班 / 大班"),
):
    """
    小程序友好版生成接口。

    负责接收老师上传的模板，生成后先落盘，再返回一个可下载的临时链接。
    """
    require_permission(user_token, "generate")
    if not (template.filename or "").lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="仅支持 .docx 格式的 Word 文件",
        )

    try:
        acts_list: list[str] = json.loads(activities) if activities else []
    except (json.JSONDecodeError, TypeError):
        acts_list = []
    if not isinstance(acts_list, list):
        acts_list = []

    template_bytes = await _read_upload_with_limit(template, MAX_UPLOAD_FILE_SIZE)

    _append_jsonl(_WEEKLY_DRAFT_LOG_FILE, {
        "ts": _utc_iso(),
        "event": "template_submit",
        "flow": "mini_template_generate",
        "template_filename": os.path.basename(template.filename or "template.docx"),
        "theme": theme,
        "phil": phil,
        "activities": acts_list,
        "child_initiative": bool(child_initiative),
    })

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

    original_name = os.path.basename(template.filename or "template.docx")
    original_name = re.sub(r'[\\/*?:"<>|]+', "_", original_name)
    if not original_name.lower().endswith(".docx"):
        original_name += ".docx"

    return _build_mini_doc_payload(
        filled_bytes=filled_bytes,
        original_name=original_name,
        export_engine=export_engine,
    )
@router.post("/mini-template/upload", tags=["核心接口"])
async def upload_mini_template(
    user_token: str = Form(..., description="登录 token"),
    template: UploadFile = File(..., description="Word 模板文件 (.docx)"),
):
    """
    小程序模板上传接口。

    - 先把老师模板保存到云端临时目录
    - 返回 template_id，后续生成只需传 template_id
    """
    require_permission(user_token, "generate")
    original_name = os.path.basename(template.filename or "template.docx")
    if not original_name.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 格式的 Word 文件")

    template_bytes = await _read_upload_with_limit(template, MAX_UPLOAD_FILE_SIZE)

    template_id = uuid4().hex
    template_path = _TEMP_TEMPLATE_DIR / f"{template_id}.docx"
    template_path.write_bytes(template_bytes)

    _TEMP_TEMPLATES[template_id] = {
        "path": str(template_path),
        "filename": original_name,
        "size": str(len(template_bytes)),
        "uploaded_at_utc": _utc_iso(),
    }
    return {
        "status": "ok",
        "template_id": template_id,
        "filename": original_name,
        "size": len(template_bytes),
    }
@router.post("/generate-mini-by-template", tags=["核心接口"])
async def generate_mini_by_template(
    user_token: str = Form(..., description="登录 token"),
    theme: str = Form(..., description="教学主题"),
    template_id: str = Form(..., description="模板ID（由 /mini-template/upload 返回）"),
    phil: str = Form("五大领域", description="教育理念"),
    activities: str = Form("[]", description="活动重点列表（JSON 数组字符串）"),
    child_initiative: bool = Form(False, description="是否有幼儿自主发起活动"),
    child_desc: str = Form("", description="幼儿自主活动描述"),
    class_level: str = Form("", description="班级类型：小班 / 中班 / 大班"),
):
    """
    小程序按 template_id 生成接口。

    先从云端临时模板池读取模板，再执行和 /generate-mini 一致的生成流程。
    """
    require_permission(user_token, "generate")
    temp_info = _TEMP_TEMPLATES.get((template_id or "").strip())
    if not temp_info:
        raise HTTPException(status_code=404, detail="模板不存在或已过期，请重新上传")

    template_path = Path(temp_info.get("path", ""))
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="模板不存在或已过期，请重新上传")

    try:
        acts_list: list[str] = json.loads(activities) if activities else []
    except (json.JSONDecodeError, TypeError):
        acts_list = []
    if not isinstance(acts_list, list):
        acts_list = []

    template_bytes = template_path.read_bytes()
    if len(template_bytes) == 0:
        raise HTTPException(status_code=400, detail="模板文件为空，请重新上传")

    _append_jsonl(_WEEKLY_DRAFT_LOG_FILE, {
        "ts": _utc_iso(),
        "event": "template_submit",
        "flow": "mini_template_generate_by_id",
        "template_id": template_id,
        "template_filename": temp_info.get("filename") or "template.docx",
        "theme": theme,
        "phil": phil,
        "activities": acts_list,
        "child_initiative": bool(child_initiative),
    })

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

    original_name = os.path.basename(temp_info.get("filename") or "template.docx")
    original_name = re.sub(r'[\\/*?:"<>|]+', "_", original_name)
    if not original_name.lower().endswith(".docx"):
        original_name += ".docx"

    return _build_mini_doc_payload(
        filled_bytes=filled_bytes,
        original_name=original_name,
        export_engine=export_engine,
    )
_EXPORT_TTL_SECONDS = 1800  # 30 分钟

@router.get("/mini-export/{token}", tags=["核心接口"])
async def download_mini_export(token: str):
    import time
    info = _TEMP_EXPORTS.get(token)
    if not info:
        raise HTTPException(status_code=404, detail="文件不存在或已过期")

    created_at = float(info.get("created_at", 0))
    if time.time() - created_at > _EXPORT_TTL_SECONDS:
        _TEMP_EXPORTS.pop(token, None)
        raise HTTPException(status_code=410, detail="下载链接已过期，请重新生成")

    path = Path(info["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")

    headers = {
        "Content-Disposition": _build_content_disposition(info["filename"]),
    }
    headers.update(_export_http_headers(info.get("engine", "python-docx-mini")))
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=info["filename"],
        headers=headers,
    )
@router.post("/transcribe-voice-mini", tags=["语音输入"])
async def transcribe_voice_mini(
    user_token: str = Form(..., description="登录 token"),
    audio: UploadFile = File(..., description="录音文件"),
    prompt: str = Form("", description="转写提示词"),
):
    """
    小程序语音输入转文字接口。

    当前优先使用 OpenAI 语音转文字能力；未配置 OPENAI_API_KEY 时返回可读错误。
    """
    require_permission(user_token, "generate")
    if voice_client is None:
        raise HTTPException(
            status_code=501,
            detail="语音转文字未配置：请先设置 OPENAI_API_KEY",
        )

    original_name = os.path.basename(audio.filename or "voice.mp3")
    suffix = Path(original_name).suffix or ".mp3"
    audio_bytes = await _read_upload_with_limit(audio, MAX_UPLOAD_FILE_SIZE, empty_detail="录音文件为空")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        with tmp_path.open("rb") as audio_file:
            transcription = voice_client.audio.transcriptions.create(
                model=VOICE_TRANSCRIBE_MODEL,
                file=audio_file,
                prompt=prompt.strip() or None,
            )
        text = getattr(transcription, "text", "") or ""
        text = text.strip()
        if not text:
            raise HTTPException(status_code=502, detail="语音识别成功，但未返回文本")
        return {
            "status": "ok",
            "text": text,
            "model": VOICE_TRANSCRIBE_MODEL,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"语音转文字失败：{e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
