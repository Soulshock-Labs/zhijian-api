"""
routers/doc_space.py — 用户文档空间路由
=============================================
接口：
  POST /doc-space/upload          上传文档 → 存原文件 + 提取MD + 存空间
  GET  /doc-space/list            列出用户所有文档
  GET  /doc-space/{doc_id}/md     读取某份文档的 MD
  DELETE /doc-space/{doc_id}      删除某份文档

这是一个独立流程，和「生成周计划」解耦：
  上传 → 存储完成 → 返回 doc_id
  生成时可带 doc_id（从空间读MD），也可临时上传文件（不存储）
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from core.auth import require_permission
from core.settings import MAX_UPLOAD_FILE_SIZE
from core.utils import _read_upload_with_limit
from word_engine.doc_reader import extract_doc_context, to_markdown, IMAGE_EXTS
from services.doc_space import (
    save_doc_to_space,
    list_user_docs,
    get_doc_md,
    delete_doc,
)

router = APIRouter(prefix="/doc-space", tags=["文档空间"])

ALLOWED_EXTS = {"docx", "pdf"} | IMAGE_EXTS


def _extract_token(request: Request, query_token: str = "") -> str:
    """从 Authorization: Bearer <token> 或 query param 中提取 user_token。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return query_token.strip()


# ── POST /doc-space/upload ────────────────────────────────────────────
@router.post("/upload")
async def upload_to_doc_space(
    user_token: str     = Form(..., description="登录 token"),
    file:    UploadFile = File(..., description="文档或图片（.docx/.pdf/.jpg/.png/.webp）"),
):
    """
    上传文档到用户空间：
    1. 读取文件
    2. 提取文本 / OCR（图片走 Kimi Vision）
    3. 转为 Markdown
    4. 存储原文件 + MD + 元数据到存储后端
    5. 返回 doc_id 和提取摘要

    这是一个独立流程，和生成周计划解耦。
    后续生成时传 doc_id，无需重复上传。
    """
    account = require_permission(user_token, "doc_space")
    account_id = str(account.get("account_id", "")).strip()

    filename = file.filename or "unknown"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的格式：{ext}，支持 .docx、.pdf、.jpg、.jpeg、.png、.webp",
        )

    file_bytes = await _read_upload_with_limit(file, MAX_UPLOAD_FILE_SIZE, empty_detail="上传文件为空")

    # ── 提取文本 → MD ──
    ctx = extract_doc_context(file_bytes, filename)
    if not ctx.ok:
        raise HTTPException(status_code=422, detail=f"文档解析失败：{ctx.error}")

    md_content = to_markdown(ctx)
    if not md_content.strip():
        raise HTTPException(status_code=422, detail="文档内容为空，无法提取有效文字")

    # ── 存入用户空间 ──
    extra = {
        "char_count":  ctx.char_count,
        "table_count": ctx.table_count,
    }
    meta = save_doc_to_space(
        user_id=account_id,
        filename=filename,
        file_bytes=file_bytes,
        md_content=md_content,
        file_type=ctx.file_type,
        extra_meta=extra,
    )

    return {
        "status":     "ok",
        "doc_id":     meta["doc_id"],
        "filename":   meta["filename"],
        "file_type":  meta["file_type"],
        "size_bytes": meta["size_bytes"],
        "md_chars":   meta["md_chars"],
        "created_at": meta["created_at"],
        "message":    f"文档已存入你的空间，共提取 {meta['md_chars']} 字",
    }


# ── GET /doc-space/list ───────────────────────────────────────────────
@router.get("/list")
async def list_docs(request: Request, user_token: str = ""):
    """列出用户空间中所有文档（按上传时间倒序）。"""
    account = require_permission(_extract_token(request, user_token), "doc_space")
    docs = list_user_docs(str(account.get("account_id", "")).strip())
    return {
        "status": "ok",
        "count":  len(docs),
        "docs":   docs,
    }


# ── GET /doc-space/{doc_id}/md ────────────────────────────────────────
@router.get("/{doc_id}/md")
async def get_doc_markdown(doc_id: str, request: Request, user_token: str = ""):
    """读取某份文档的 Markdown 内容（供预览或 Agent 使用）。"""
    account = require_permission(_extract_token(request, user_token), "doc_space")
    md = get_doc_md(str(account.get("account_id", "")).strip(), doc_id)
    if md is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {
        "status": "ok",
        "doc_id": doc_id,
        "md":     md,
        "chars":  len(md),
    }


# ── DELETE /doc-space/{doc_id} ────────────────────────────────────────
@router.delete("/{doc_id}")
async def remove_doc(doc_id: str, request: Request, user_token: str = ""):
    """从用户空间删除某份文档（原文件 + MD + 元数据）。"""
    account = require_permission(_extract_token(request, user_token), "doc_space")
    ok = delete_doc(str(account.get("account_id", "")).strip(), doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "ok", "doc_id": doc_id, "message": "已删除"}
