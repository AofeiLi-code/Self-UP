"""
ai_client.py — 随身系统的 HTTP 层

封装 OpenAI 兼容 SDK（指向 DeepSeek API），对外提供：
  - build_system_prompt : 从 services.ai_service 透传，业务语义在那里维护
  - call_claude         : 向 DeepSeek 发起单次异步对话请求
"""

import os

from openai import AsyncOpenAI

# 业务语义（人设 + 世界观映射）集中在 services/ai_service.py 维护
# 此处 re-export，保持所有调用方的 import 路径不变
from services.ai_service import build_system_prompt as build_system_prompt  # noqa: F401

# 延迟初始化，避免启动时因缺少 API Key 而崩溃
_client: AsyncOpenAI | None = None

# deepseek-chat → DeepSeek-V3.2 非思考模式
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"


def get_client() -> AsyncOpenAI:
    """获取（或初始化）DeepSeek 异步客户端。读取 DEEPSEEK_API_KEY 环境变量。"""
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未找到 DEEPSEEK_API_KEY 环境变量，请复制 .env.example 为 .env 并填入密钥"
            )
        _client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
    return _client


async def call_claude(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 300,
) -> str:
    """向 DeepSeek V3.2 发起异步请求，返回纯文本回复。"""
    client = get_client()
    response = await client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system_prompt}, *messages],
    )
    return response.choices[0].message.content
