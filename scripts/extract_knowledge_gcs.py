#!/usr/bin/env python3
"""
知识库提取脚本 — 从 GCS 读取教案 PDF，用 AI 提取结构化内容，存回 GCS。

用法：
    python scripts/extract_knowledge_gcs.py

环境变量（复用 .env）：
    DASHSCOPE_API_KEY   DeepSeek / DashScope API Key
    DASHSCOPE_BASE_URL  API 基础 URL
    AI_MODEL            视觉模型（如 deepseek-chat，如有视觉模型请换成 deepseek-vl）
    GCS_KNOWLEDGE_BUCKET  GCS bucket 名，默认 apt-decorator-473807-t1-knowledge
    GCP_PROJECT_ID        GCP 项目 ID
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

try:
    from google.cloud import storage as gcs
except ImportError:
    print("[ERROR] 缺少 google-cloud-storage，请运行：pip install google-cloud-storage")
    sys.exit(1)

try:
    import pypdf
except ImportError:
    print("[ERROR] 缺少 pypdf，请运行：pip install pypdf")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("[ERROR] 缺少 openai，请运行：pip install openai")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────
API_KEY      = os.getenv("DASHSCOPE_API_KEY", "")
BASE_URL     = os.getenv("DASHSCOPE_BASE_URL", "https://api.deepseek.com/v1")
AI_MODEL     = os.getenv("EXTRACT_AI_MODEL", os.getenv("AI_MODEL", "deepseek-chat"))
PROJECT_ID   = os.getenv("GCP_PROJECT_ID", "apt-decorator-473807-t1")
BUCKET_NAME  = os.getenv("GCS_KNOWLEDGE_BUCKET", f"{PROJECT_ID}-knowledge")
KB_PREFIX    = "knowledge_base"
OUTPUT_KEY   = f"{KB_PREFIX}/indexes/curriculum_database.json"
PROGRESS_KEY = f"{KB_PREFIX}/indexes/extract_progress.json"

# 班级目录 → class_level 标签的映射
CLASS_LEVEL_MAP = {
    "小班上学期": "小班", "小班下学期": "小班",
    "中班上学期": "中班", "中班下学期": "中班",
    "大班上学期": "大班", "大班下学期": "大班",
    "小班上学期一日活动": "小班", "小班下学期一日活动（新版）": "小班",
    "中班上学期一日活动": "中班", "中班下学期一日活动（新版）": "中班",
    "大班上学期一日活动": "大班", "大班下学期一日活动（新版）": "大班",
}

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ── GCS 工具 ──────────────────────────────────────────────────────────

def get_gcs_client():
    return gcs.Client(project=PROJECT_ID)


def list_pdfs(bucket) -> list[gcs.Blob]:
    blobs = list(bucket.list_blobs(prefix=f"{KB_PREFIX}/library/"))
    return [b for b in blobs if b.name.lower().endswith(".pdf")]


def download_blob(blob: gcs.Blob, dest: Path) -> Path:
    blob.download_to_filename(str(dest))
    return dest


def upload_json(bucket, key: str, data: dict) -> None:
    blob = bucket.blob(key)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8"
    )


def load_json_from_gcs(bucket, key: str) -> dict:
    blob = bucket.blob(key)
    if not blob.exists():
        return {}
    return json.loads(blob.download_as_text(encoding="utf-8"))


# ── PDF 文字提取 ───────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> str:
    """用 pypdf 提取 PDF 文字。图片型 PDF 会返回空字符串。"""
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text.strip())
        return "\n\n".join(pages_text)
    except Exception as e:
        print(f"    [WARN] pypdf 提取失败: {e}")
        return ""


def extract_first_page_as_base64(pdf_path: Path) -> str | None:
    """将 PDF 第一页渲染为 PNG base64（需要 pdf2image + poppler）。"""
    try:
        from pdf2image import convert_from_path  # type: ignore
        images = convert_from_path(str(pdf_path), first_page=1, last_page=1, dpi=150)
        if not images:
            return None
        buf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        images[0].save(buf.name, format="PNG")
        buf.close()
        with open(buf.name, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        os.unlink(buf.name)
        return b64
    except ImportError:
        return None
    except Exception as e:
        print(f"    [WARN] pdf2image 失败: {e}")
        return None


# ── AI 提取 ───────────────────────────────────────────────────────────

EXTRACT_SYSTEM = """你是幼儿园课程专家。
请从教案内容中提取关键信息，严格以 JSON 格式返回，不含 markdown 代码块。
JSON 结构：
{
  "themes": ["主题1", "主题2"],
  "week_label": "第N周 主题名",
  "goals": ["目标1", "目标2"],
  "domains": ["健康","语言","社会","科学","艺术"],
  "activities": [
    {
      "name": "活动名称",
      "day": "周一",
      "domain": "健康",
      "materials": ["材料1"],
      "process_summary": "核心玩法/过程简述（100字内）",
      "keywords": ["关键词"]
    }
  ],
  "songs": ["儿歌/歌谣名称或内容"],
  "keywords": ["长大","自理","成长"],
  "class_level_hint": "小班/中班/大班（如无法判断则留空）"
}"""


def ai_extract_from_text(text: str, filename: str) -> dict | None:
    """用 AI 从纯文字提取结构化内容。"""
    if not text.strip():
        return None
    prompt = f"文件名：{filename}\n\n内容：\n{text[:6000]}"
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.strip("```json").strip("```").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"    [WARN] AI 文字提取失败: {e}")
        return None


def ai_extract_from_image(b64_png: str, filename: str) -> dict | None:
    """用视觉 AI 从图片提取结构化内容（需要模型支持图片）。"""
    prompt = f"这是一份幼儿园教案图片，文件名：{filename}。请提取所有关键教案信息。"
    try:
        resp = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_png}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.strip("```json").strip("```").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"    [WARN] AI 图片提取失败（模型可能不支持视觉）: {e}")
        return None


# ── 班级信息从路径推断 ─────────────────────────────────────────────────

def infer_class_level(blob_name: str) -> str:
    for key, level in CLASS_LEVEL_MAP.items():
        if key in blob_name:
            return level
    if "小班" in blob_name:
        return "小班"
    if "中班" in blob_name:
        return "中班"
    if "大班" in blob_name:
        return "大班"
    return ""


def infer_semester(blob_name: str) -> str:
    if "上学期" in blob_name:
        return "上学期"
    if "下学期" in blob_name:
        return "下学期"
    return ""


# ── 主流程 ────────────────────────────────────────────────────────────

def process_pdf(blob: gcs.Blob, tmp_dir: Path) -> dict | None:
    """下载 PDF，提取结构化内容，返回记录或 None。"""
    filename = Path(blob.name).name
    print(f"  处理: {filename} ({blob.size // 1024 // 1024}MB)")

    tmp_pdf = tmp_dir / filename
    try:
        download_blob(blob, tmp_pdf)
    except Exception as e:
        print(f"    [ERROR] 下载失败: {e}")
        return None

    # Step 1: 尝试 pypdf 文字提取
    text = extract_text_from_pdf(tmp_pdf)
    extracted = None

    if len(text) > 100:
        print(f"    → pypdf 提取到 {len(text)} 字，使用文字模式")
        extracted = ai_extract_from_text(text, filename)
    else:
        print(f"    → 图片型 PDF，尝试视觉模式")
        b64 = extract_first_page_as_base64(tmp_pdf)
        if b64:
            extracted = ai_extract_from_image(b64, filename)
        if not extracted:
            # 视觉失败时，用文件名推断基础信息
            print(f"    → 仅用文件名推断元数据")
            extracted = {
                "themes": [filename.replace(".pdf", "")],
                "keywords": [filename.replace(".pdf", "")],
                "activities": [],
                "songs": [],
            }

    if not extracted:
        return None

    # 补充元数据
    extracted["doc_id"]    = blob.name
    extracted["filename"]  = filename
    extracted["gcs_path"]  = f"gs://{BUCKET_NAME}/{blob.name}"
    extracted["class_level"] = (
        extracted.get("class_level_hint") or infer_class_level(blob.name)
    )
    extracted["semester"]  = infer_semester(blob.name)
    extracted["extracted_at_utc"] = datetime.now(timezone.utc).isoformat()

    tmp_pdf.unlink(missing_ok=True)
    return extracted


def main():
    if not API_KEY:
        print("[ERROR] 未设置 DASHSCOPE_API_KEY")
        sys.exit(1)

    print(f"[INFO] 连接 GCS bucket: {BUCKET_NAME}")
    gcs_client = get_gcs_client()
    bucket = gcs_client.bucket(BUCKET_NAME)

    # 加载已有进度（支持断点续传）
    progress = load_json_from_gcs(bucket, PROGRESS_KEY)
    done_ids: set[str] = set(progress.get("done", []))

    # 加载已有数据库
    db = load_json_from_gcs(bucket, OUTPUT_KEY)
    records: list[dict] = db.get("records", [])
    existing_ids = {r["doc_id"] for r in records}

    print(f"[INFO] 已处理: {len(done_ids)} 份，已有记录: {len(records)} 条")

    pdfs = list_pdfs(bucket)
    print(f"[INFO] 发现 PDF: {len(pdfs)} 份")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        for i, blob in enumerate(pdfs, 1):
            if blob.name in done_ids or blob.name in existing_ids:
                print(f"[{i}/{len(pdfs)}] 跳过（已处理）: {Path(blob.name).name}")
                continue

            print(f"[{i}/{len(pdfs)}]", end=" ")
            record = process_pdf(blob, tmp_path)

            if record:
                records.append(record)
                done_ids.add(blob.name)
                print(f"    ✅ 提取成功: {record.get('themes', [])}")
            else:
                done_ids.add(blob.name)  # 失败也标记，避免重复
                print(f"    ⚠️  提取失败，跳过")

            # 每处理 5 份保存一次进度
            if i % 5 == 0:
                _save_progress(bucket, records, done_ids)
                print(f"    [进度已保存]")

            time.sleep(0.5)  # 避免 API 频率限制

    # 最终保存
    _save_progress(bucket, records, done_ids)
    print(f"\n[完成] 共提取 {len(records)} 份文档")
    print(f"[结果] gs://{BUCKET_NAME}/{OUTPUT_KEY}")


def _save_progress(bucket, records: list, done_ids: set):
    db = {
        "version": "rag-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "doc_count": len(records),
        "records": records,
    }
    upload_json(bucket, OUTPUT_KEY, db)
    upload_json(bucket, PROGRESS_KEY, {
        "done": list(done_ids),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    main()
