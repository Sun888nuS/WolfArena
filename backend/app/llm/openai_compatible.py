"""OpenAI-compatible 第三方中转站 provider。"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.llm.base import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    LlmProviderError,
)


class OpenAICompatibleProvider:
    """调用 OpenAI-compatible `/chat/completions` 接口的 provider。"""

    def __init__(self, settings: Settings) -> None:
        """保存运行时配置。"""
        self._settings = settings

    @property
    def base_url(self) -> str:
        """返回配置的中转站基础 URL。"""
        return self._settings.llm_base_url

    @property
    def model(self) -> str:
        """返回配置的默认模型名。"""
        return self._settings.llm_model

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """调用配置的 OpenAI-compatible 聊天补全接口。"""
        if not self._settings.llm_api_key_configured:
            raise LlmProviderError("LLM_API_KEY is not configured.")

        payload = self._payload_for(request)
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        timeout = httpx.Timeout(self._settings.llm_timeout_seconds)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - 统一包装 provider 失败
            raise LlmProviderError("OpenAI-compatible request failed.") from exc

        content = _content_from_response_data(data)

        if not isinstance(content, str) or not content.strip():
            raise LlmProviderError("OpenAI-compatible response content is empty.")

        return ChatCompletionResponse(
            content=content,
            model=str(data.get("model") or payload["model"]),
        )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """调用配置的 OpenAI-compatible 流式聊天补全接口。"""
        if not self._settings.llm_api_key_configured:
            raise LlmProviderError("LLM_API_KEY is not configured.")

        payload = {**self._payload_for(request), "stream": True}
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        timeout = httpx.Timeout(self._settings.llm_timeout_seconds)
        raw_lines: list[str] = []
        saw_sse = False
        yielded = False

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, headers=self._headers(), json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            if not saw_sse:
                                raw_lines.append(line)
                            continue

                        saw_sse = True
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        content = _content_from_stream_data(json.loads(data))
                        if content:
                            yielded = True
                            yield content

            if not saw_sse and raw_lines:
                content = _content_from_response_data(json.loads("\n".join(raw_lines)))
                if content:
                    yielded = True
                    yield content
        except LlmProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一包装 provider 失败
            raise LlmProviderError("OpenAI-compatible stream request failed.") from exc

        if not yielded:
            raise LlmProviderError("OpenAI-compatible stream response content is empty.")

    def _payload_for(self, request: ChatCompletionRequest) -> dict[str, Any]:
        """构建 OpenAI-compatible 聊天补全请求体。"""
        payload: dict[str, Any] = {
            "model": request.model or self._settings.llm_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
        }
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": request.response_schema,
            }
        return payload

    def _headers(self) -> dict[str, str]:
        """构建 OpenAI-compatible API 请求头。"""
        return {
            "Authorization": f"Bearer {self._settings.llm_api_key}",
            "Content-Type": "application/json",
        }


def _content_from_response_data(data: dict[str, Any]) -> str:
    """从非流式响应中提取 assistant content。"""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmProviderError("OpenAI-compatible response is malformed.") from exc
    if not isinstance(content, str):
        raise LlmProviderError("OpenAI-compatible response is malformed.")
    return content


def _content_from_stream_data(data: dict[str, Any]) -> str:
    """从流式响应 chunk 中提取 assistant delta content。"""
    try:
        delta = data["choices"][0].get("delta") or {}
        content = delta.get("content")
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise LlmProviderError("OpenAI-compatible stream response is malformed.") from exc
    return content if isinstance(content, str) else ""
