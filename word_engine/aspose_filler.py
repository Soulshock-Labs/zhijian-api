"""
word_engine.aspose_filler — Aspose.Words 填充引擎（可选）

ENABLE_ASPOSE_WORDS=1 时启用。默认关闭，因 CLR 级崩溃无法由 try/except 捕获。
所有 _aw_* 函数均通过懒加载隔离，只在首次真实调用时触发 import。
"""
from __future__ import annotations

import importlib
import io
import logging
import os

logger = logging.getLogger(__name__)

# 模块级 aw = None，懒加载，防止 import 阶段崩溃
aw = None  # type: ignore


def _env_truthy(name: str, default: str = "0") -> bool:
    raw = os.getenv(name, default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


ENABLE_ASPOSE_WORDS = _env_truthy("ENABLE_ASPOSE_WORDS", "0")
APP_VERSION = os.getenv("APP_VERSION", "1.2.1")


def _aw_lazy_import():
    global aw
    if aw is None:
        aw = importlib.import_module("aspose.words")
    return aw


def _aw_require() -> None:
    if not ENABLE_ASPOSE_WORDS:
        raise RuntimeError("Aspose.Words 已关闭（设置 ENABLE_ASPOSE_WORDS=1 可启用）")
    if aw is None:
        _aw_lazy_import()
    if aw is None:
        raise RuntimeError("未安装 aspose-words，无法导出 Word（请检查 requirements / 容器镜像）")


def _aw_doc_from_bytes(data: bytes) -> "aw.Document":
    _aw_require()
    return aw.Document(io.BytesIO(data))


def _aw_doc_to_bytes(doc: "aw.Document") -> bytes:
    _aw_require()
    out = io.BytesIO()
    doc.save(out, aw.SaveFormat.DOCX)
    return out.getvalue()


def _aw_cell_dedup_key(cell) -> int:
    return id(cell)


def _aw_node_as_table(node) -> "aw.tables.Table":
    _aw_require()
    try:
        return node.as_table()
    except Exception:
        return aw.tables.Table.cast(node)


def _aw_stamp_export_provenance(doc: "aw.Document") -> None:
    """在文档属性中写入导出标记，便于确认走了 Aspose 管线。"""
    try:
        doc.built_in_document_properties.comments = (
            f"小纸笺导出 · v{APP_VERSION} · 排版引擎 Aspose.Words"
        )
        cdp = doc.custom_document_properties
        for name, val in (("ZhibanExportEngine", "Aspose.Words"), ("ZhibanAppVersion", APP_VERSION)):
            try:
                cdp.add(name, val)
            except Exception:
                pass
    except Exception:
        pass


def _export_http_headers(engine: str) -> dict[str, str]:
    return {"X-Export-Engine": engine, "X-App-Version": APP_VERSION}


def _aw_cell_text(cell: "aw.tables.Cell") -> str:
    try:
        return cell.to_string(aw.SaveFormat.TEXT).strip()
    except Exception:
        return ""


def _aw_cell_has_color(cell: "aw.tables.Cell") -> bool:
    """非透明/非白色底纹视为模板固定区。"""
    try:
        shading = cell.cell_format.shading
        bg = shading.background_pattern_color.to_argb()
        fg = shading.foreground_pattern_color.to_argb()
        if bg not in (0, -1, 0x00FFFFFF, 0xFFFFFFFF):
            return True
        if fg not in (0, -1, 0x00FFFFFF, 0xFFFFFFFF):
            return True
    except Exception:
        return False
    return False


def _aw_copy_run_font(src_run: "aw.Run", dst_run: "aw.Run") -> None:
    try:
        dst_run.font.name = src_run.font.name
        dst_run.font.size = src_run.font.size
        dst_run.font.bold = src_run.font.bold
        dst_run.font.italic = src_run.font.italic
        dst_run.font.color = src_run.font.color
    except Exception:
        pass


def _aw_write_cell_preserve_style(doc: "aw.Document", cell: "aw.tables.Cell", text: str) -> None:
    """向单元格写入文本（多段换行），兼容合并单元格结构。"""
    _aw_require()
    lines = (text or "").split("\n") or [""]
    while cell.paragraphs.count > 0:
        cell.paragraphs[0].remove()
    for line in lines:
        p = aw.Paragraph(doc)
        r = aw.Run(doc, line)
        p.append_child(r)
        cell.append_child(p)


def _aw_get_day_col_map(table: "aw.tables.Table") -> tuple[int, list[int]]:
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "周一", "周二", "周三", "周四", "周五")
    for ri in range(table.rows.count):
        row = table.rows[ri]
        day_cols = [ci for ci in range(row.cells.count) if any(d in _aw_cell_text(row.cells[ci]) for d in weekdays)]
        if len(day_cols) >= 3:
            return ri, sorted(day_cols)
    return -1, []


def _fill_word_template_aspose_bytes(cleaned_bytes: bytes, fill_data: dict[str, str]) -> bytes:
    """Aspose 回填；失败时由上层捕获并回退 docx。"""
    from .field_map import match_field, _ACTIVITY_FIELDS, _weekday_tag_from_header

    _aw_require()
    doc = _aw_doc_from_bytes(cleaned_bytes)
    filled_cells: set[int] = set()
    tables = doc.get_child_nodes(aw.NodeType.TABLE, True)

    for ti in range(tables.count):
        table = _aw_node_as_table(tables[ti])
        day_header_ri, day_cols = _aw_get_day_col_map(table)

        if day_header_ri >= 0 and len(day_cols) >= 3:
            header_cache: dict[int, str] = {}
            hdr_row = table.rows[day_header_ri]
            for day_ci in day_cols:
                if day_ci < hdr_row.cells.count:
                    header_cache[day_ci] = _aw_cell_text(hdr_row.cells[day_ci])

            for row_idx in range(day_header_ri):
                row = table.rows[row_idx]
                for col_idx in range(row.cells.count):
                    cell = row.cells[col_idx]
                    field = match_field(_aw_cell_text(cell))
                    content = fill_data.get(field) if field else None
                    if not content:
                        continue
                    for ci in range(col_idx + 1, row.cells.count):
                        cand = row.cells[ci]
                        if match_field(_aw_cell_text(cand)) or _aw_cell_has_color(cand):
                            continue
                        key = _aw_cell_dedup_key(cand)
                        if key in filled_cells:
                            break
                        filled_cells.add(key)
                        _aw_write_cell_preserve_style(doc, cand, content)
                        break

            hdr_row = table.rows[day_header_ri]
            for day_ci, txt in header_cache.items():
                if day_ci < hdr_row.cells.count:
                    _aw_write_cell_preserve_style(doc, hdr_row.cells[day_ci], txt)

            current_field: str | None = None
            for row_idx in range(day_header_ri + 1, table.rows.count):
                row = table.rows[row_idx]
                if row.cells.count == 0:
                    continue
                col0_field = match_field(_aw_cell_text(row.cells[0]))
                if col0_field:
                    current_field = col0_field
                row_field = current_field
                if row.cells.count > 1:
                    col1_field = match_field(_aw_cell_text(row.cells[1]))
                    if col1_field and col1_field in _ACTIVITY_FIELDS:
                        row_field = col1_field
                content = fill_data.get(row_field) if row_field else None
                if not content:
                    continue
                for day_ci in day_cols:
                    if day_ci >= row.cells.count:
                        continue
                    target = row.cells[day_ci]
                    if _aw_cell_has_color(target):
                        continue
                    day_tag = _weekday_tag_from_header(header_cache.get(day_ci, ""))
                    if day_tag and row_field:
                        content = fill_data.get(f"{row_field}__{day_tag}", content)
                    key = _aw_cell_dedup_key(target)
                    if key in filled_cells:
                        continue
                    filled_cells.add(key)
                    _aw_write_cell_preserve_style(doc, target, content)
        else:
            for row_idx in range(table.rows.count):
                row = table.rows[row_idx]
                for col_idx in range(row.cells.count):
                    cell = row.cells[col_idx]
                    field = match_field(_aw_cell_text(cell))
                    content = fill_data.get(field) if field else None
                    if not content:
                        continue
                    target = None
                    if col_idx + 1 < row.cells.count:
                        cand = row.cells[col_idx + 1]
                        if not match_field(_aw_cell_text(cand)) and not _aw_cell_has_color(cand):
                            target = cand
                    if target is None and row_idx + 1 < table.rows.count and col_idx < table.rows[row_idx + 1].cells.count:
                        cand = table.rows[row_idx + 1].cells[col_idx]
                        if not match_field(_aw_cell_text(cand)) and not _aw_cell_has_color(cand):
                            target = cand
                    if target is None:
                        continue
                    key = _aw_cell_dedup_key(target)
                    if key in filled_cells:
                        continue
                    filled_cells.add(key)
                    _aw_write_cell_preserve_style(doc, target, content)

    _aw_stamp_export_provenance(doc)
    return _aw_doc_to_bytes(doc)
