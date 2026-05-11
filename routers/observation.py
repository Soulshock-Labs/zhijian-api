from __future__ import annotations

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

import io, json, re

from core.auth import require_permission
from core.settings import MAX_UPLOAD_FILE_SIZE
from core.utils import _read_upload_with_limit
from services.generate_service import _build_observation_docx_bytes, generate_observation_content
from word_engine.aspose_filler import _export_http_headers
from word_engine.docx_filler import _build_content_disposition
router = APIRouter()
@router.post("/preview-observation", tags=["拍照观察"])
async def preview_observation(
    user_token: str = Form(...),
    theme: str = Form(...),
    child_name: str = Form(""),
    scene: str = Form("活动现场"),
    note: str = Form(""),
    phil: str = Form("五大领域"),
    photo_names: str = Form("[]"),
):
    require_permission(user_token, "observe")
    try:
        parsed = json.loads(photo_names) if photo_names else []
        names = [str(x) for x in parsed if str(x).strip()]
    except Exception:
        names = []
    content = generate_observation_content(
        theme=theme,
        child_name=child_name,
        scene=scene,
        note=note,
        phil=phil,
        photo_names=names,
    )
    return {"status": "ok", "content": content}
@router.post("/generate-observation", tags=["拍照观察"])
async def generate_observation(
    user_token: str = Form(...),
    theme: str = Form(...),
    child_name: str = Form(""),
    scene: str = Form("活动现场"),
    note: str = Form(""),
    phil: str = Form("五大领域"),
    photos: list[UploadFile] = File(default=[]),
):
    require_permission(user_token, "observe")
    valid_photos = [p for p in photos if (p.filename or "").strip()]
    for photo in valid_photos:
        await _read_upload_with_limit(photo, MAX_UPLOAD_FILE_SIZE, empty_detail="观察图片为空")
    photo_names = [str(p.filename).strip() for p in valid_photos]
    content = generate_observation_content(
        theme=theme,
        child_name=child_name,
        scene=scene,
        note=note,
        phil=phil,
        photo_names=photo_names,
    )
    filled_bytes = _build_observation_docx_bytes(
        content=content,
        theme=theme,
        child_name=child_name,
        scene=scene,
        phil=phil,
        note=note,
        photo_names=photo_names,
    )
    child = child_name.strip() or "幼儿"
    original_name = re.sub(r'[\\/*?:"<>|]+', "_", f"{theme}_{child}_观察记录.docx")
    h = {"Content-Disposition": _build_content_disposition(original_name)}
    h.update(_export_http_headers("python-docx-observation"))
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=h,
    )
@router.post("/generate-observation-mini", tags=["拍照观察"])
async def generate_observation_mini(
    user_token: str = Form(...),
    theme: str = Form(...),
    child_name: str = Form(""),
    scene: str = Form("活动现场"),
    note: str = Form(""),
    phil: str = Form("五大领域"),
    photo_names: str = Form("[]"),
):
    """
    小程序友好版观察记录生成接口。

    仅依赖文本和照片名列表，避免小程序端多文件上传的额外复杂度。
    """
    require_permission(user_token, "observe")
    try:
        parsed = json.loads(photo_names) if photo_names else []
        names = [str(x) for x in parsed if str(x).strip()]
    except Exception:
        names = []
    content = generate_observation_content(
        theme=theme,
        child_name=child_name,
        scene=scene,
        note=note,
        phil=phil,
        photo_names=names,
    )
    filled_bytes = _build_observation_docx_bytes(
        content=content,
        theme=theme,
        child_name=child_name,
        scene=scene,
        phil=phil,
        note=note,
        photo_names=names,
    )
    child = child_name.strip() or "幼儿"
    original_name = re.sub(r'[\\/*?:"<>|]+', "_", f"{theme}_{child}_观察记录.docx")
    h = {"Content-Disposition": _build_content_disposition(original_name)}
    h.update(_export_http_headers("python-docx-observation-mini"))
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=h,
    )
