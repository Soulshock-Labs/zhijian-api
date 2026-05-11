"""
services/doc_space.py — 用户文档空间业务逻辑
=============================================
职责：
  每个用户有独立的文档空间，存储上传的原文件和提取的 MD。
  Agent 扫描时从这里检索用户自己的文档。

存储路径规范（在 StorageBackend 内的逻辑路径）：
  users/{user_id}/docs/{doc_id}/original.{ext}   ← 原始文件
  users/{user_id}/docs/{doc_id}/content.md        ← 提取的 Markdown
  users/{user_id}/docs/{doc_id}/meta.json         ← 元数据（文件名/类型/时间/大小）
  users/{user_id}/docs/index.json                 ← 该用户所有文档索引

Agent 扫描时调用：
  list_user_docs(user_id)           → 文档索引列表
  get_doc_md(user_id, doc_id)       → 某份文档的 MD 内容
  get_all_docs_md(user_id)          → 所有文档 MD 拼合（注入 prompt 用）
"""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from core.storage import get_storage
from core.utils import _utc_iso

logger = logging.getLogger(__name__)

# Agent 扫描时单用户最大注入字符数（避免超 token）
MAX_AGENT_SCAN_CHARS = 8000


# ══════════════════════════════════════════════════════════════════════
# 路径工具
# ══════════════════════════════════════════════════════════════════════

def _doc_prefix(user_id: str, doc_id: str) -> str:
    return f"users/{user_id}/docs/{doc_id}"

def _original_path(user_id: str, doc_id: str, ext: str) -> str:
    return f"{_doc_prefix(user_id, doc_id)}/original.{ext}"

def _md_path(user_id: str, doc_id: str) -> str:
    return f"{_doc_prefix(user_id, doc_id)}/content.md"

def _meta_path(user_id: str, doc_id: str) -> str:
    return f"{_doc_prefix(user_id, doc_id)}/meta.json"

def _index_path(user_id: str) -> str:
    return f"users/{user_id}/docs/index.json"


# ══════════════════════════════════════════════════════════════════════
# 写入：上传文档到用户空间
# ══════════════════════════════════════════════════════════════════════

def save_doc_to_space(
    user_id: str,
    filename: str,
    file_bytes: bytes,
    md_content: str,
    file_type: str,
    extra_meta: dict | None = None,
) -> dict:
    """
    把原文件 + MD 存入用户空间，更新索引，返回 doc_meta。

    参数：
      user_id     用户唯一标识
      filename    原始文件名
      file_bytes  原始文件二进制
      md_content  已提取的 Markdown 文本
      file_type   "docx" / "pdf" / "image"
      extra_meta  额外元数据（可选，如 char_count / table_count）
    """
    store = get_storage()
    doc_id = uuid4().hex
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "bin"

    # ── 1. 存原文件 ──
    content_type_map = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf":  "application/pdf",
        "jpg":  "image/jpeg", "jpeg": "image/jpeg",
        "png":  "image/png",
        "webp": "image/webp",
        "gif":  "image/gif",
    }
    ct = content_type_map.get(ext, "application/octet-stream")
    store.put(_original_path(user_id, doc_id, ext), file_bytes, content_type=ct)
    logger.info("原文件已存储：user=%s doc=%s ext=%s size=%d", user_id, doc_id, ext, len(file_bytes))

    # ── 2. 存 MD ──
    store.put_text(_md_path(user_id, doc_id), md_content, content_type="text/markdown; charset=utf-8")
    logger.info("MD 已存储：user=%s doc=%s chars=%d", user_id, doc_id, len(md_content))

    # ── 3. 存元数据 ──
    meta: dict = {
        "doc_id":      doc_id,
        "user_id":     user_id,
        "filename":    filename,
        "file_type":   file_type,
        "ext":         ext,
        "size_bytes":  len(file_bytes),
        "md_chars":    len(md_content),
        "created_at":  _utc_iso(),
        **(extra_meta or {}),
    }
    store.put_text(_meta_path(user_id, doc_id), json.dumps(meta, ensure_ascii=False, indent=2))

    # ── 4. 更新用户文档索引 ──
    _update_user_index(user_id, meta)

    return meta


def _update_user_index(user_id: str, new_meta: dict) -> None:
    """在用户索引 index.json 中追加新文档记录。"""
    store = get_storage()
    path = _index_path(user_id)
    existing_text = store.get_text(path)
    if existing_text:
        try:
            index: list[dict] = json.loads(existing_text)
        except Exception:
            index = []
    else:
        index = []

    # 去重（同 doc_id 只保留最新）
    index = [d for d in index if d.get("doc_id") != new_meta["doc_id"]]
    index.append(new_meta)

    # 按时间倒序
    index.sort(key=lambda d: d.get("created_at", ""), reverse=True)

    store.put_text(path, json.dumps(index, ensure_ascii=False, indent=2))
    logger.info("用户文档索引已更新：user=%s 共 %d 份", user_id, len(index))


# ══════════════════════════════════════════════════════════════════════
# 读取：供 Agent 扫描
# ══════════════════════════════════════════════════════════════════════

def list_user_docs(user_id: str) -> list[dict]:
    """返回用户所有文档的元数据列表（按时间倒序）。"""
    store = get_storage()
    text = store.get_text(_index_path(user_id))
    if not text:
        return []
    try:
        return json.loads(text)
    except Exception:
        return []


def get_doc_md(user_id: str, doc_id: str) -> str | None:
    """读取某份文档的 MD 内容。"""
    return get_storage().get_text(_md_path(user_id, doc_id))


def get_all_docs_md(user_id: str, max_chars: int = MAX_AGENT_SCAN_CHARS) -> str:
    """
    拼合用户所有文档的 MD，供 Agent 注入 prompt。
    按时间倒序取，超出 max_chars 截断。
    """
    docs = list_user_docs(user_id)
    if not docs:
        return ""

    parts: list[str] = []
    total = 0

    for meta in docs:
        doc_id = meta.get("doc_id", "")
        filename = meta.get("filename", "")
        created_at = meta.get("created_at", "")[:10]  # 只取日期
        md = get_doc_md(user_id, doc_id) or ""
        if not md.strip():
            continue

        header = f"\n---\n## 文档：{filename}（{created_at}）\n"
        chunk = header + md

        if total + len(chunk) > max_chars:
            # 尽量塞进去，截断
            remaining = max_chars - total
            if remaining > len(header) + 100:
                parts.append(chunk[:remaining] + "\n…（已截断）")
            break

        parts.append(chunk)
        total += len(chunk)

    if not parts:
        return ""

    return (
        f"# 老师的文档空间（共 {len(docs)} 份）\n"
        + "\n".join(parts)
        + f"\n\n---\n以上是老师上传的参考文档，请结合这些内容理解老师的教学风格和偏好。"
    )


def delete_doc(user_id: str, doc_id: str) -> bool:
    """删除某份文档（原文件 + MD + 元数据 + 更新索引）。"""
    store = get_storage()
    meta_text = store.get_text(_meta_path(user_id, doc_id))
    if not meta_text:
        return False

    try:
        meta = json.loads(meta_text)
        ext = meta.get("ext", "bin")
        store.delete(_original_path(user_id, doc_id, ext))
    except Exception:
        pass

    store.delete(_md_path(user_id, doc_id))
    store.delete(_meta_path(user_id, doc_id))

    # 从索引移除
    path = _index_path(user_id)
    existing_text = store.get_text(path)
    if existing_text:
        try:
            index = [d for d in json.loads(existing_text) if d.get("doc_id") != doc_id]
            store.put_text(path, json.dumps(index, ensure_ascii=False, indent=2))
        except Exception:
            pass

    logger.info("文档已删除：user=%s doc=%s", user_id, doc_id)
    return True
