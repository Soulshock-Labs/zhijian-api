from __future__ import annotations

import logging
import importlib
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from core.settings import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    VOICE_TRANSCRIBE_MODEL,
    APP_VERSION,
)

load_dotenv()
logger = logging.getLogger(__name__)

# 注意：不要在模块导入阶段直接 import aspose.words。
# 在部分环境中该导入会触发 CLR 级崩溃（进程退出），无法由 try/except 捕获。
aw = None  # type: ignore


def _aw_lazy_import():
    global aw
    if aw is None:
        aw = importlib.import_module("aspose.words")  # noqa: PLC0415
    return aw


# 安全开关：Aspose 在部分环境会触发 CLR 级崩溃（无法由 Python try/except 捕获）。
# 默认关闭，显式配置 ENABLE_ASPOSE_WORDS=1 再启用。
from core.settings import _env_truthy

ENABLE_ASPOSE_WORDS = _env_truthy("ENABLE_ASPOSE_WORDS", "0")
if not ENABLE_ASPOSE_WORDS:
    logger.warning("Aspose.Words 默认关闭：将使用 python-docx 导出（可设 ENABLE_ASPOSE_WORDS=1 开启）")
else:
    logger.info("Aspose.Words 开关已开启：将在首次导出时尝试懒加载")

# 生成内容安全开关：默认不允许静默回退 Mock，避免线上“看似成功但内容跑偏”。
ALLOW_MOCK_CONTENT = _env_truthy("ALLOW_MOCK_CONTENT", "0")

# 阿里云百炼 / OpenAI-compatible client（当前实际为 Moonshot）
client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
)

# DeepSeek client
deepseek_client = (
    OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    if DEEPSEEK_API_KEY
    else None
)

# Qwen / 阿里云 DashScope client
qwen_client = (
    OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL)
    if QWEN_API_KEY
    else None
)

voice_client = (
    OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    if OPENAI_API_KEY
    else None
)

# Firestore（懒加载，Cloud Run 上有 ADC 自动认证）
try:
    from google.cloud import firestore as _firestore
    _FS_CLIENT: Optional["_firestore.Client"] = None

    def _fs() -> "_firestore.Client":
        global _FS_CLIENT
        if _FS_CLIENT is None:
            _FS_CLIENT = _firestore.Client()
        return _FS_CLIENT

    FIRESTORE_ENABLED = True
except Exception:
    FIRESTORE_ENABLED = False
    _FS_CLIENT = None

    def _fs():
        return None

# 运行时临时状态
_TEMP_EXPORTS: dict[str, dict[str, str]] = {}

_TEMP_TEMPLATES: dict[str, dict[str, str]] = {}
