"""
kindergarten_template_cleaner.py
净空幼儿园周计划 Word 模板，保留结构，清空内容槽位。

支持：
  - 含 {{Tag}} 强锚点
  - 纯结构推断（词典 + 首列 / 星期表头行）
  - 含颜色底纹的模板（如粉色标签格，w:shd / 段落底纹）

使用方式：
  python kindergarten_template_cleaner.py input.docx output_净空模板.docx [--report]

API：
  clean_docx_bytes(template_bytes) -> bytes   # 供 FastAPI main.py 调用
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

# ── 命名空间 ────────────────────────────────────────────────────────────────
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


# ── 词典（与 TEMPLATE_STANDARD v1.1 同步） ──────────────────────────────────
MODULE_KEYWORDS = {
    # 元信息
    "活动主题",
    "教学主题",
    "本月主题",
    "单元主题",
    "班级",
    "时间",
    "日期",
    "周次",
    "天气",
    "教育理念",
    # 周计划主行
    "生活活动",
    "一日生活",
    "学习活动",
    "教学活动",
    "集中活动",
    "游戏活动",
    "区域活动",
    "区角活动",
    "户外活动",
    "体育活动",
    "户外游戏",
    "家园互动",
    "家园共育",
    "家长工作",
    "家园社区互动",
    "离园活动",
    "环境创设",
    "环创",
    "评价与反思",
    "反思",
    "小结",
    "上周情况分析与本周工作重点",
    "指导要点",
    "重点目标",
    "早谈",
    "早  谈",
    # 子模块标签（col 1）
    "区域活动",
    "自主活动",
    "集体活动",
    "自主",
    "集体",
    # 星期表头
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "星    期",
    "星期",
    # 时间段
    "上午",
    "下午",
    # 日教案
    "活动导入",
    "导入",
    "活动过程",
    "基本过程",
    "活动延伸",
    "延伸",
    "活动反思",
    "教师反思",
    "观察要点",
}

SUB_LABEL_KEYWORDS = {
    "区域活动",
    "自主活动",
    "集体活动",
    "自主",
    "集体",
    "上午",
    "下午",
}

# {{Tag}} 正则：允许 run 拆分后重新拼合检测
TAG_PATTERN = re.compile(r"\{\{([^}]+?)\}\}")


# ── 文档类型识别 ──────────────────────────────────────────────────────────
def detect_doc_type(all_cell_texts: list[str]) -> str:
    flat = " ".join(all_cell_texts)
    has_days = bool(re.search(r"星期[一二三四五]|周[一二三四五]", flat))
    has_week_title = bool(re.search(r"第\s*\d+\s*周|周计划", flat))
    has_daily = bool(re.search(r"活动导入|活动过程|活动延伸|活动反思", flat))
    has_tags = bool(TAG_PATTERN.search(flat))

    if has_daily:
        return "daily_plan"
    if has_days or has_week_title:
        if has_tags:
            return "weekly_grid_tagged"
        return "weekly_grid"
    return "general_plan"


# ── 颜色底纹检测（单元格内任一处 w:shd，非白即保护） ───────────────────────
def cell_has_color_fill(tc) -> bool:
    """非白色、非 AUTO 底色 → 视为受保护模板区（含 tcPr 与段落 pPr 底纹）。"""
    for shd in tc.findall(f".//{qn('shd')}"):
        fill = (shd.get(qn("fill")) or "").strip().upper()
        if fill and fill not in ("AUTO", "FFFFFF"):
            return True
        # 部分主题色仅用 themeFill
        if shd.get(qn("themeFill")) or shd.get(qn("themeFillShade")):
            return True
    return False


# ── 单元格文本提取 ────────────────────────────────────────────────────────
def cell_text(tc) -> str:
    return "".join(t.text or "" for t in tc.findall(f".//{qn('t')}"))


# ── 识别"星期表头行"索引 ────────────────────────────────────────────────
DAY_PATTERN = re.compile(r"星期[一二三四五]|周[一二三四五]")


def find_day_header_row(rows) -> int:
    """
    返回含 ≥3 个「星期X / 周X」表头单元格的行索引。
    找不到时返回 -1（不得默认 0，否则会把第 0 行整行误当作星期表头保护，例如 R0C1 活动主题值无法净空）。
    """
    for ri, row in enumerate(rows):
        cells = row.findall(qn("tc"))
        cell_texts = [cell_text(tc).strip() for tc in cells]
        day_hits = sum(1 for t in cell_texts if DAY_PATTERN.search(t))
        if day_hits >= 3:
            return ri
    return -1


def find_all_day_header_rows(template_bytes: bytes) -> list[int]:
    """
    解析 document.xml，对每个表格返回星期表头行索引；未识别到则为 -1。
    供 /template/analyze 报告与调试验收。
    """
    try:
        with zipfile.ZipFile(io.BytesIO(template_bytes)) as z:
            xml = z.read("word/document.xml")
    except Exception:
        return []
    root = etree.fromstring(xml)
    tables = root.findall(f".//{{{W}}}tbl")
    out: list[int] = []
    for tbl in tables:
        rows = tbl.findall(qn("tr"))
        out.append(find_day_header_row(rows) if rows else -1)
    return out


# ── 保护区判定 ────────────────────────────────────────────────────────────
def is_protected(
    row_idx: int,
    col_idx: int,
    tc,
    doc_type: str,
    total_rows: int,
    col0_texts: list[str],
    day_header_row: int = -1,
) -> tuple[bool, str]:
    """
    返回 (protected: bool, reason: str)
    优先级：色块 > 星期表头行 > 首列 > 关键词 > sub-label > vmerge
    """
    text = cell_text(tc).strip()
    # Word 有时把"集体\n活动"拆成多段——拼合去空行后再做关键词匹配
    text_compact = "".join(text.split())

    # P1: 颜色底纹
    if cell_has_color_fill(tc):
        return True, "color_fill"

    # P2: 星期表头行（动态识别；仅当确实命中含 ≥3 个星期列的行，day_header_row >= 0）
    if day_header_row >= 0 and row_idx == day_header_row:
        return True, "day_header_row"

    # P3: 首列
    if col_idx == 0:
        return True, "first_col"

    # P4: 关键词匹配（模块标签单元格）
    # 同时检查原文和去空行拼合版，兼容 Word 多段拆字的情况
    if text in MODULE_KEYWORDS or text_compact in MODULE_KEYWORDS:
        return True, f"module_keyword:{text_compact}"

    # P5: sub-label（col=1 的子模块标签，用于嵌套子行）
    if col_idx == 1 and (text in SUB_LABEL_KEYWORDS or text_compact in SUB_LABEL_KEYWORDS):
        return True, f"sub_label:{text_compact}"

    # P6: vMerge continue 空单元格 → 合并延续格，跟随主格判定
    vmerge = tc.find(f".//{qn('vMerge')}")
    if vmerge is not None:
        val = vmerge.get(qn("val"), "")
        if val != "restart" and text == "":
            return True, "vmerge_continue"

    return False, ""


# ── 文本清空（保留格式） ──────────────────────────────────────────────────
def clear_cell_text(tc) -> None:
    """
    清空单元格所有文本，保留：
    - 段落 <w:p> 结构（保留第一个 <w:pPr>）
    - run 格式 <w:rPr>（但清空 <w:t>）
    - 单元格属性 <w:tcPr>（边框、合并、底纹等）
    """
    paras = tc.findall(qn("p"))
    if not paras:
        return

    first_para = paras[0]
    for p in paras[1:]:
        tc.remove(p)

    runs = first_para.findall(qn("r"))
    keeper_run = None
    for r in runs:
        if r.find(qn("rPr")) is not None and keeper_run is None:
            keeper_run = r
        else:
            first_para.remove(r)

    if keeper_run is not None:
        t_el = keeper_run.find(qn("t"))
        if t_el is not None:
            t_el.text = ""
    elif runs:
        r0 = first_para.findall(qn("r"))
        for r in r0[1:]:
            first_para.remove(r)
        if r0:
            t_el = r0[0].find(qn("t"))
            if t_el is not None:
                t_el.text = ""


# ── {{Tag}} 单元格处理（保留占位符，清除其他内容） ───────────────────────
def clear_tagged_cell(tc) -> None:
    """
    保留 {{...}} 占位符文本，清空其余教师填写内容。
    {{Tag}} 可能被 Word 拆分成多个 run。
    """
    paras = tc.findall(qn("p"))
    if not paras:
        return

    first_para = paras[0]
    for p in paras[1:]:
        tc.remove(p)

    runs = first_para.findall(qn("r"))
    if not runs:
        return

    run_texts = []
    for r in runs:
        t = r.find(qn("t"))
        run_texts.append(t.text or "" if t is not None else "")

    combined = "".join(run_texts)
    m = TAG_PATTERN.search(combined)
    if not m:
        clear_cell_text(tc)
        return

    tag_start, tag_end = m.start(), m.end()

    pos = 0
    tag_runs = []
    non_tag_runs = []
    for r, rt in zip(runs, run_texts):
        run_start = pos
        run_end = pos + len(rt)
        if run_end > tag_start and run_start < tag_end:
            tag_runs.append(r)
        else:
            non_tag_runs.append(r)
        pos = run_end

    for r in non_tag_runs:
        first_para.remove(r)


# ── 主处理流程 ────────────────────────────────────────────────────────────
def clean_docx(
    input_path: str | Path,
    output_path: str | Path,
    emit_report: bool = False,
    *,
    silent: bool = False,
) -> dict:
    input_path = Path(input_path)
    output_path = Path(output_path)

    tmpdir = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(input_path, "r") as z:
            z.extractall(tmpdir)

        doc_xml_path = tmpdir / "word" / "document.xml"
        tree = etree.parse(str(doc_xml_path))
        root = tree.getroot()

        tables = root.findall(f".//{qn('tbl')}")
        report: dict = {
            "input": str(input_path),
            "output": str(output_path),
            "tables": [],
        }

        for tbl_idx, tbl in enumerate(tables):
            rows = tbl.findall(qn("tr"))

            all_texts = [cell_text(tc) for row in rows for tc in row.findall(qn("tc"))]
            doc_type = detect_doc_type(all_texts)
            col0_texts = [
                cell_text(row.findall(qn("tc"))[0]) if row.findall(qn("tc")) else ""
                for row in rows
            ]
            day_header_row = find_day_header_row(rows)

            tbl_report = {
                "table_index": tbl_idx,
                "doc_type": doc_type,
                "rows": len(rows),
                "day_header_row": day_header_row,
                "mappings": [],
            }

            for ri, row in enumerate(rows):
                cells = row.findall(qn("tc"))
                for ci, tc in enumerate(cells):
                    text = cell_text(tc).strip()
                    has_tag = bool(TAG_PATTERN.search(cell_text(tc)))
                    protected, reason = is_protected(
                        ri, ci, tc, doc_type, len(rows), col0_texts, day_header_row
                    )

                    if protected:
                        status = "skipped_protected"
                    elif has_tag:
                        clear_tagged_cell(tc)
                        status = "cleared_tagged"
                    else:
                        clear_cell_text(tc)
                        status = "cleared"

                    if status != "skipped_protected" or reason:
                        tbl_report["mappings"].append(
                            {
                                "row": ri,
                                "col": ci,
                                "text_preview": text[:30],
                                "status": status,
                                "reason": reason or status,
                            }
                        )

            report["tables"].append(tbl_report)

        tree.write(
            str(doc_xml_path),
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for f in tmpdir.rglob("*"):
                if f.is_file():
                    zout.write(f, f.relative_to(tmpdir))

        if emit_report:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif not silent:
            cleared = sum(
                1
                for t in report["tables"]
                for m in t["mappings"]
                if str(m["status"]).startswith("cleared")
            )
            protected = sum(
                1
                for t in report["tables"]
                for m in t["mappings"]
                if m["status"] == "skipped_protected"
            )
            print(f"✓ 净空完成: 已清空 {cleared} 个内容格，保留 {protected} 个保护格")
            print(f"  输出: {output_path}")

        return report
    finally:
        shutil.rmtree(tmpdir)


def clean_docx_bytes(template_bytes: bytes) -> bytes:
    """内存入参 / 出参，供 FastAPI 使用。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        inp = tmp / "_in.docx"
        out = tmp / "_out.docx"
        inp.write_bytes(template_bytes)
        clean_docx(inp, out, emit_report=False, silent=True)
        return out.read_bytes()
    finally:
        shutil.rmtree(tmp)


# ── CLI ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python kindergarten_template_cleaner.py input.docx output.docx [--report]")
        sys.exit(1)

    emit = "--report" in sys.argv
    clean_docx(sys.argv[1], sys.argv[2], emit_report=emit)
