from __future__ import annotations

import os
import secrets
import string
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_VERSION = os.getenv("APP_VERSION", "1.2.1")
APP_ENV = str(os.getenv("APP_ENV", "development")).strip().lower() or "development"

def _env_truthy(name: str, default: str = "0") -> bool:
    raw = os.getenv(name, default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

DASHSCOPE_BASE_URL = os.getenv(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

AI_MODEL = os.getenv("AI_MODEL", "qwen-max")

AI_MODEL_FAST = os.getenv("AI_MODEL_FAST", "qwen-turbo")

# ── DeepSeek ──
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# ── 阿里云 DashScope（Qwen） ──
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

VOICE_TRANSCRIBE_MODEL = os.getenv("VOICE_TRANSCRIBE_MODEL", "whisper-1")
MAX_UPLOAD_FILE_SIZE = int(os.getenv("MAX_UPLOAD_FILE_SIZE", str(10 * 1024 * 1024)) or (10 * 1024 * 1024))

_BASE_DIR = Path(__file__).resolve().parent.parent

_KNOWLEDGE_BASE_DIR = _BASE_DIR / "knowledge_base"

_KNOWLEDGE_INDEX_FILE = _KNOWLEDGE_BASE_DIR / "indexes" / "knowledge_index.json"

_KNOWLEDGE_ROUTE_FILE = _KNOWLEDGE_BASE_DIR / "indexes" / "profile_routes.json"

_TEMPLATE_STATS_FILE = _BASE_DIR / "template_download_stats.json"

_DEFAULT_TEMPLATE_STATS = {
    "weekly": 0,  # 周/活动计划模板
    "daily": 0,   # 日教案模板
    "cleaned": 0, # 净空版模板下载
}

_APP_STATS_FILE = _BASE_DIR / "app_public_stats.json"

_FEEDBACK_LOG_FILE = _BASE_DIR / "feedback_messages.jsonl"

_WEEKLY_DRAFT_LOG_FILE = _BASE_DIR / "weekly_draft_sessions.jsonl"

_REGISTER_LOG_FILE = _BASE_DIR / "registrations.jsonl"

_REDEEM_CODES_FILE = _BASE_DIR / "redeem_codes.json"

_REDEEM_CODES_GCS_URI = os.getenv("REDEEM_CODES_GCS_URI", "").strip()

_REDEEM_LOG_FILE = _BASE_DIR / "redeem_logs.jsonl"

_USER_SERVICE_FILE = _BASE_DIR / "user_services.json"

_USER_ACCOUNTS_FILE  = _BASE_DIR / "user_accounts.json"
_ACCOUNT_INDEX_FILE  = _BASE_DIR / "account_index.json"   # phone/openid → account_id 反查表
_MEMBER_NO_FILE      = _BASE_DIR / "member_no_counter.json"  # 会员号计数器

_WEBHOOK_RETRY_FILE = _BASE_DIR / "partner_webhook_retry.jsonl"

_TEMP_EXPORT_DIR = Path(tempfile.gettempdir()) / "smart-teacher-assistant-exports"
_TEMP_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

_TEMP_TEMPLATE_DIR = Path(tempfile.gettempdir()) / "smart-teacher-assistant-templates"
_TEMP_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_APP_STATS = {
    "home_visits": 0,
    "module_clicks": 0,
    "feedback_count": 0,
    "register_count": 0,
}

_DEFAULT_REDEEM_CODES: list[dict] = []

def _parse_partner_tokens(raw: str) -> set[str]:
    items = [part.strip() for part in str(raw or "").split(",")]
    return {item for item in items if item}

PARTNER_REDEEM_TOKENS = _parse_partner_tokens(os.getenv("PARTNER_REDEEM_TOKENS", ""))

PARTNER_REDEEM_SOURCE = str(os.getenv("PARTNER_REDEEM_SOURCE", "third_party_mall")).strip() or "third_party_mall"

def _parse_webhook_urls(raw: str) -> dict[str, str]:
    """解析 PARTNER_WEBHOOK_URLS 环境变量，格式：token1:url1,token2:url2"""
    result: dict[str, str] = {}
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        token, sep, url = part.partition(":")
        if sep and token.strip() and url.strip():
            result[token.strip()] = url.strip()
    return result

PARTNER_WEBHOOK_URLS: dict[str, str] = _parse_webhook_urls(os.getenv("PARTNER_WEBHOOK_URLS", ""))

TEMPLATE_STANDARD_V116 = {
    "version": "v1.2.0",
    "principles": [
        "星期表头行动态识别（含≥3个星期列），非整表首行硬保护；首列默认保护",
        "上色单元格视为固定模板区，不可覆盖",
        "仅对可填槽位进行净空和内容写入",
        "保留字体、字号、段落、边框、合并关系等样式",
    ],
    "recognition_order": [
        "文档类型识别（周计划/日教案/活动计划）",
        "主标签识别（主题/目标/准备/过程/反思）",
        "主行主列到子槽位映射（含拆分单元格）",
        "内容写入与净空（仅 fillable slots）",
    ],
    "keyword_groups": {
        "meta": ["班级", "日期", "天气", "活动主题", "教学主题", "教育理念"],
        "plan": ["活动目标", "活动准备", "学习活动", "区域活动", "户外活动", "评价与反思"],
        "daily": ["活动导入", "活动过程", "活动延伸", "活动反思", "观察要点"],
    },
}

_CODE_ALPHABET = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "OI15S")

_CODE_PREFIX_MAP = {"membership": "M", "balance": "B", "quota": "Q"}

_FRONTEND = str(_BASE_DIR / "index.html")


def _default_cors_origins() -> list[str]:
    if APP_ENV == "production":
        return [
            "https://zhijian.me",
            "https://www.zhijian.me",
            "https://test.zhijian.me",
        ]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://test.zhijian.me",
    ]


def _parse_cors_origins(raw: str) -> list[str]:
    items = [item.strip() for item in str(raw or "").split(",")]
    values = [item for item in items if item]
    return values or _default_cors_origins()


CORS_ALLOW_ORIGINS = _parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS", ""))
