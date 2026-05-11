"""
word_engine — Word 模板填充引擎包

子模块：
  field_map      — 关键字映射规则 + 教育理念词库
  template_tools — 模板净空 / 分析 / 内置模板构建
  docx_filler    — python-docx 回填（核心路径）
  aspose_filler  — Aspose.Words 回填（可选，精排）
"""
from .field_map import match_field, CELL_KEYWORD_MAP, PHILOSOPHY_HINTS, CLASS_LEVEL_HINTS
from .template_tools import clean_template_keep_style, analyze_template_docx
from .docx_filler import fill_word_template, _fill_word_template_docx_bytes, docx_to_pdf_bytes, docx_to_images_bytes

__all__ = [
    "match_field",
    "CELL_KEYWORD_MAP",
    "PHILOSOPHY_HINTS",
    "CLASS_LEVEL_HINTS",
    "clean_template_keep_style",
    "analyze_template_docx",
    "fill_word_template",
    "_fill_word_template_docx_bytes",
    "docx_to_pdf_bytes",
    "docx_to_images_bytes",
]
