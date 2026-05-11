#!/usr/bin/env python3
"""
从 knowledge_base/ 目录读取所有 PDF，提取纯文本，
分块保存到 knowledge_base/indexes/text_corpus.jsonl

运行方式：
  cd /path/to/smart-teacher-assistant
  python scripts/extract_pdf_text.py

生成后同步到 GCS：
  bash scripts/sync_knowledge_base_to_gcs.sh
"""
import json
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("[ERROR] 请先安装依赖: pip install pypdf")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge_base"
OUT_FILE = KB_DIR / "indexes" / "text_corpus.jsonl"

CHUNK_SIZE = 400   # 每段字符数（中文约 200 词）
CHUNK_OVERLAP = 80  # 段落间重叠，保持上下文连贯


def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'
                  r'a-zA-Z0-9，。！？、：；「」『』（）【】\s]', '', text)
    return text.strip()


def chunk_text(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if len(chunk) > 50:  # 过滤太短的块
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def extract_pdf(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            parts.append(t)
        return "\n".join(parts)
    except Exception as e:
        print(f"  [WARN] 读取失败: {e}")
        return ""


def main():
    if not KB_DIR.exists():
        print(f"[ERROR] 知识库目录不存在: {KB_DIR}")
        sys.exit(1)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(KB_DIR.rglob("*.pdf"))
    if not pdf_files:
        print(f"[ERROR] 未找到 PDF 文件: {KB_DIR}")
        sys.exit(1)

    print(f"[INFO] 找到 {len(pdf_files)} 个 PDF 文件")
    print(f"[INFO] 输出文件: {OUT_FILE}\n")

    total_chunks = 0
    skipped = 0

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for i, pdf_path in enumerate(pdf_files):
            try:
                rel = pdf_path.relative_to(KB_DIR)
            except ValueError:
                rel = pdf_path.name

            print(f"[{i+1:3d}/{len(pdf_files)}] {rel}")
            text = extract_pdf(pdf_path)

            if not text.strip():
                print(f"         → 跳过（扫描版或无文本）")
                skipped += 1
                continue

            chunks = chunk_text(text)
            if not chunks:
                skipped += 1
                continue

            for j, chunk in enumerate(chunks):
                record = {
                    "source": str(rel),
                    "chunk_id": j,
                    "text": chunk,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_chunks += 1

            print(f"         → {len(chunks)} 段")

    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"\n[SUCCESS] 完成！")
    print(f"  文档数：{len(pdf_files) - skipped} / {len(pdf_files)}（{skipped} 个跳过）")
    print(f"  总段落：{total_chunks}")
    print(f"  文件大小：{size_mb:.1f} MB")
    print(f"\n下一步：bash scripts/sync_knowledge_base_to_gcs.sh")


if __name__ == "__main__":
    main()
