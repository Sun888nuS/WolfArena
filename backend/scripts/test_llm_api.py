"""本地 OpenAI-compatible 大模型接口冒烟测试。

用法示例：
    python scripts/test_llm_api.py
    python scripts/test_llm_api.py --model gpt-4o-mini
    python scripts/test_llm_api.py --model deepseek-chat --structured
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings  # noqa: E402


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="测试当前中转站模型 API 是否可用。")
    parser.add_argument(
        "--model",
        default="",
        help="临时覆盖 .env 中的 LLM_MODEL，例如 gpt-4o-mini。",
    )
    parser.add_argument(
        "--prompt",
        default="请用一句中文回复：狼人杀 AI 模型连通性测试成功。",
        help="发送给模型的测试问题。",
    )
    parser.add_argument(
        "--structured",
        action="store_true",
        help="测试 response_format=json_schema，接近游戏内结构化决策调用。",
    )
    return parser.parse_args()


def build_payload(model: str, prompt: str, structured: bool) -> dict[str, Any]:
    """构建聊天补全请求体。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是狼人杀项目的模型连通性测试助手，只输出简短中文。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    if structured:
        payload["messages"][1]["content"] = (
            "请返回一个 JSON 对象，字段为 status、message。"
            "status 固定为 ok，message 用中文说明模型 API 可用。"
        )
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "llm_smoke_test",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "status": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["status", "message"],
                },
            },
        }

    return payload


def format_error(response: httpx.Response) -> str:
    """从失败的 HTTP 响应中提取紧凑错误信息。"""
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = response.text
    return json.dumps(body, ensure_ascii=False, indent=2)


async def main() -> int:
    """执行大模型连通性冒烟测试。"""
    args = parse_args()
    settings = get_settings()
    model = args.model.strip() or settings.llm_model

    print("=== LLM API 本地测试 ===")
    print(f"Base URL: {settings.llm_base_url}")
    print(f"Model: {model}")
    print(f"API Key: {settings.masked_llm_api_key or '未配置'}")
    print(f"Structured: {'是' if args.structured else '否'}")

    if not settings.llm_api_key_configured:
        print("\n失败：未配置 LLM_API_KEY，请先在 backend/.env 或 ours/.env 中配置。")
        return 2

    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = build_payload(model, args.prompt, args.structured)

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        print(f"\n失败：请求中转站异常：{exc}")
        return 1

    if response.status_code >= 400:
        print(f"\n失败：HTTP {response.status_code}")
        print(format_error(response))
        return 1

    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    returned_model = data.get("model", model)

    print("\n成功：模型 API 可用")
    print(f"Returned model: {returned_model}")
    print("Response:")
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
