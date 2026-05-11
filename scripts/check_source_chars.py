#!/usr/bin/env python3
"""
check_source_chars.py — 源码字符污染检查
============================================
用途：发布前扫描，发现会破坏 Python 解析或关键代码声明的字符污染。

规则：
- Python 文件中，字符串/注释之外出现中文弯引号，直接阻断
- 路由、def、class、import 等关键代码行中，字符串/注释之外出现全角标点，直接阻断
- 注释中的中文弯引号只警告（不阻断）

用法：
    python scripts/check_source_chars.py
    # 或在项目根目录：
    python zhijian-api/scripts/check_source_chars.py
"""
from __future__ import annotations

import sys
import token
import tokenize
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════════════

# 阻断级：这些字符出现在任何代码行都直接报错（中文弯引号不可能合法）
BLOCK_CHARS: dict[str, str] = {
    "\u201c": "中文左弯引号",
    "\u201d": "中文右弯引号",
    "\u2018": "中文左单引号",
    "\u2019": "中文右单引号",
}

# 阻断级（仅限关键代码行）：路由、def、class、import 中
BLOCK_CHARS_KEYLINE: dict[str, str] = {
    "\uff1a": "全角冒号",
    "\uff0c": "全角逗号",
    "\uff1b": "全角分号",
    "\uff08": "全角左括号",
    "\uff09": "全角右括号",
}

# 警告级：注释中的中文标点只警告
WARN_CHARS: dict[str, str] = {
    "\u201c": "中文左弯引号",
    "\u201d": "中文右弯引号",
}

# 扫描的文件类型
SCAN_EXTENSIONS = {".py"}

# 跳过的目录
SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", ".pytest_cache"}

# 关键代码行的前缀判断（简化版）
KEY_LINE_PREFIXES = ("@", "def ", "class ", "import ", "from ")


# ══════════════════════════════════════════════════════════════════════
# 核心逻辑
# ══════════════════════════════════════════════════════════════════════

def _is_key_code_line(line: str) -> bool:
    """判断是否为关键代码行（路由、函数定义、import等）。"""
    stripped = line.lstrip()
    return stripped.startswith(KEY_LINE_PREFIXES)


def _line_span_map(path: Path) -> dict[int, list[tuple[int, int, int]]]:
    """返回每一行的 token 覆盖区间: (start_col, end_col, token_type)。"""
    spans: dict[int, list[tuple[int, int, int]]] = {}
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in {token.STRING, tokenize.COMMENT}:
                start_line, start_col = tok.start
                end_line, end_col = tok.end
                for line_no in range(start_line, end_line + 1):
                    line_start = start_col if line_no == start_line else 0
                    line_end = end_col if line_no == end_line else sys.maxsize
                    spans.setdefault(line_no, []).append((line_start, line_end, tok.type))
    return spans


def _token_type_at_col(
    spans: dict[int, list[tuple[int, int, int]]], lineno: int, col: int
) -> int | None:
    """返回当前位置命中的 token 类型。"""
    for start_col, end_col, tok_type in spans.get(lineno, []):
        if start_col <= col < end_col:
            return tok_type
    return None


def scan_file(path: Path) -> tuple[list[str], list[str]]:
    """
    扫描单个文件。
    返回：(errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return [f"{path}: 无法读取 ({e})"], []

    try:
        span_map = _line_span_map(path)
    except tokenize.TokenError as e:
        return [f"{path}: tokenize 失败 ({e})"], []

    for lineno, line in enumerate(lines, 1):
        is_key = _is_key_code_line(line)
        for col, ch in enumerate(line):
            tok_type = _token_type_at_col(span_map, lineno, col)

            if tok_type == tokenize.COMMENT and ch in WARN_CHARS:
                warnings.append(
                    f"  {path}:{lineno}  警告: 注释中出现{WARN_CHARS[ch]}({ch!r})"
                )
                continue

            if tok_type in {token.STRING, tokenize.COMMENT}:
                continue

            if ch in BLOCK_CHARS:
                level = "关键代码行" if is_key else "代码行"
                errors.append(
                    f"  {path}:{lineno}  阻断: {level}出现{BLOCK_CHARS[ch]}({ch!r})"
                )
                continue

            if is_key and ch in BLOCK_CHARS_KEYLINE:
                errors.append(
                    f"  {path}:{lineno}  阻断: 关键代码行出现{BLOCK_CHARS_KEYLINE[ch]}({ch!r})"
                )

    return errors, warnings


def main() -> int:
    """扫描项目，返回退出码。"""
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    project_root = Path(__file__).resolve().parent.parent
    errors: list[str] = []
    warnings: list[str] = []
    scanned = 0

    for path in project_root.rglob("*"):
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        scanned += 1
        e, w = scan_file(path)
        errors.extend(e)
        warnings.extend(w)

    # ═════════════════════════════════════════════════════════════════
    # 输出结果
    # ═════════════════════════════════════════════════════════════════
    print(f"扫描完成: {scanned} 个 Python 文件")
    print()

    if warnings:
        print(f"⚠️  警告 ({len(warnings)} 处，不阻断发布):")
        for w in warnings:
            print(w)
        print()

    if errors:
        print(f"❌ 阻断错误 ({len(errors)} 处):")
        for e in errors:
            print(e)
        print()
        print("请修复上述错误后再发布。")
        return 1

    print("✅ 未检测到字符污染，可以发布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
