from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from core.state import logger

def _append_jsonl(path: Path, payload: dict) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("写入 JSONL 失败（%s）：%s", path.name, e)

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _parse_iso_datetime(value: str) -> datetime | None:
    """解析 ISO 格式日期时间字符串，无时区时默认补 UTC，非法值返回 None。"""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def _parse_gs_uri(uri: str) -> tuple[str, str]:
    u = str(uri or "").strip()
    if not u.startswith("gs://"):
        raise ValueError("invalid gs uri")
    rest = u[5:]
    if "/" not in rest:
        raise ValueError("invalid gs uri")
    bucket, _, blob = rest.partition("/")
    if not bucket or not blob:
        raise ValueError("invalid gs uri")
    return bucket, blob

def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


async def _read_upload_with_limit(file: UploadFile, max_bytes: int, *, empty_detail: str = "上传文件为空") -> bytes:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail=empty_detail)
    if len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail=f"文件超过 {max_bytes // (1024 * 1024)}MB 限制")
    return payload
