from __future__ import annotations

from fastapi import HTTPException

def _raise_if_invalid_dashscope_key(exc: Exception) -> None:
    """
    DashScope / OpenAI 兼容客户端在 Key 错误时通常返回 401。
    与「未配置」区分：环境变量有值但无效时，/health 仍会显示已配置，需给出可操作说明。
    """
    text = str(exc)
    low = text.lower()
    if (
        "401" in text
        or "invalid_api_key" in low
        or "incorrect api key" in low
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "阿里云百炼 API Key 无效或已过期。请在部署环境（Cloud Run 环境变量/密钥）"
                "更新 DASHSCOPE_API_KEY 为百炼控制台生成的完整密钥。"
                "使用通义 Qwen 时请保持 DASHSCOPE_BASE_URL="
                "https://dashscope.aliyuncs.com/compatible-mode/v1，"
                "勿将 DeepSeek / OpenAI 的 Key 与百炼 Base URL 混用。"
            ),
        )
