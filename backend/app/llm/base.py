"""LLM provider 抽象契约。"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatMessage:
    """发送给模型 provider 的单条聊天消息。"""

    role: str  # system/user/assistant 等角色
    content: str  # 消息正文


@dataclass(frozen=True)
class ChatCompletionRequest:
    """与具体 provider 无关的聊天补全请求。"""

    messages: list[ChatMessage]  # 输入消息列表
    model: str  # 模型名称
    temperature: float = 0.7  # 采样温度
    response_schema: dict[str, Any] | None = None  # 可选结构化输出 schema


@dataclass(frozen=True)
class ChatCompletionResponse:
    """与具体 provider 无关的聊天补全响应。"""

    content: str  # 模型返回文本
    model: str  # 实际返回模型名


class LlmProvider(Protocol):
    """具体 LLM provider 需要实现的协议。"""

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """根据聊天补全请求返回模型响应。"""

    def stream_complete(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        """根据聊天补全请求增量返回模型文本片段。"""


class LlmProviderError(RuntimeError):
    """LLM provider 无法返回有效响应时抛出的异常。"""
