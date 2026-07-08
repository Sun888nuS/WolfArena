"""在线文本 Agent。

本模块只负责为单个 AI 玩家构造可见视角、调用 OpenAI-compatible provider，
并把模型输出校验为结构化决策。它不修改游戏真相状态。
"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any

from pydantic import ValidationError

from app.agents.personas import persona_for_player
from app.agents.prompts import build_decision_prompt, build_speech_prompt
from app.agents.schemas import AgentDecision
from app.agents.validators import validate_agent_decision
from app.config import get_settings
from app.core.models import GameState
from app.core.visibility import build_player_view
from app.llm.base import ChatCompletionRequest, ChatMessage, LlmProviderError
from app.llm.openai_compatible import OpenAICompatibleProvider


SpeechStreamCallback = Callable[[str, str], Awaitable[None] | None]
SPEECH_MAX_CHARS = 240
SPEECH_STREAM_SOFT_TIMEOUT_SECONDS = 20


class TextAgent:
    """单个 AI 玩家对应的在线文本 Agent。"""

    def __init__(self, player_id: str, *, player_index: int) -> None:
        """初始化玩家 id、固定人格和在线模型 provider。"""
        self.player_id = player_id
        self.persona = persona_for_player(player_index)
        self.provider = OpenAICompatibleProvider(get_settings())
        self.last_source = "not_called"
        self.last_error = ""

    async def decide(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
        stream_speech: bool = False,
        on_speech_delta: SpeechStreamCallback | None = None,
    ) -> AgentDecision:
        """基于当前合法视角返回已校验的 AI 决策。"""
        settings = get_settings()

        view = build_player_view(
            state,
            self.player_id,
            public_memory=public_memory,
            private_memories=private_memories,
            wolf_shared_memory=wolf_shared_memory,
        )
        messages = build_decision_prompt(view, self.persona, task)
        request = ChatCompletionRequest(
            messages=[ChatMessage(**message) for message in messages],
            model=settings.llm_model,
            temperature=0.4,
        )

        try:
            content = await self._complete_content(
                request,
                stream_speech=stream_speech,
                on_speech_delta=on_speech_delta,
            )
            raw = _parse_json_object(content)
            decision = AgentDecision.model_validate(raw)
            self.last_source = "llm"
            self.last_error = ""
            return validate_agent_decision(state, self.player_id, decision)
        except (json.JSONDecodeError, ValidationError, LlmProviderError, ValueError) as exc:
            self.last_source = "error"
            self.last_error = str(exc)[:180]
            raise LlmProviderError(f"Online agent decision failed for {self.player_id}.") from exc

    async def decide_sheriff_order(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        """让警长选择白天发言方向。"""
        return await self._raw_decide(
            state,
            task,
            public_memory=public_memory,
            private_memories=private_memories,
            wolf_shared_memory=wolf_shared_memory,
            error_context="sheriff order",
        )

    async def decide_sheriff_handoff(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
    ) -> AgentDecision:
        """让出局警长选择警徽移交对象。"""
        return await self._raw_decide(
            state,
            task,
            public_memory=public_memory,
            private_memories=private_memories,
            wolf_shared_memory=wolf_shared_memory,
            error_context="sheriff handoff",
        )

    async def _raw_decide(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None,
        private_memories: dict[str, dict[str, object]] | None,
        wolf_shared_memory: dict[str, object] | None,
        error_context: str,
    ) -> AgentDecision:
        """调用在线模型并返回未经过阶段校验的结构化决策。"""
        settings = get_settings()
        view = build_player_view(
            state,
            self.player_id,
            public_memory=public_memory,
            private_memories=private_memories,
            wolf_shared_memory=wolf_shared_memory,
        )
        messages = build_decision_prompt(view, self.persona, task)
        request = ChatCompletionRequest(
            messages=[ChatMessage(**message) for message in messages],
            model=settings.llm_model,
            temperature=0.4,
        )
        try:
            response = await self.provider.complete(request)
            raw = _parse_json_object(response.content)
            decision = AgentDecision.model_validate(raw)
            self.last_source = "llm"
            self.last_error = ""
            return decision
        except (json.JSONDecodeError, ValidationError, LlmProviderError, ValueError) as exc:
            self.last_source = "error"
            self.last_error = str(exc)[:180]
            raise LlmProviderError(f"Online {error_context} decision failed for {self.player_id}.") from exc

    async def decide_streamed_speech(
        self,
        state: GameState,
        task: str,
        *,
        public_memory: dict[str, object] | None = None,
        private_memories: dict[str, dict[str, object]] | None = None,
        wolf_shared_memory: dict[str, object] | None = None,
        on_speech_delta: SpeechStreamCallback | None = None,
    ) -> AgentDecision:
        """为公开发言生成纯文本流，并返回可落盘的发言决策。"""
        settings = get_settings()
        view = build_player_view(
            state,
            self.player_id,
            public_memory=public_memory,
            private_memories=private_memories,
            wolf_shared_memory=wolf_shared_memory,
        )
        request = ChatCompletionRequest(
            messages=[ChatMessage(**message) for message in build_speech_prompt(view, self.persona, task)],
            model=settings.llm_model,
            temperature=0.55,
        )
        try:
            speech = await self._complete_streamed_speech_text(
                request,
                on_speech_delta=on_speech_delta,
                timeout_seconds=min(
                    settings.llm_timeout_seconds,
                    SPEECH_STREAM_SOFT_TIMEOUT_SECONDS,
                ),
            )
            decision = AgentDecision(action_type="speak", speech=speech)
            self.last_source = "llm"
            self.last_error = ""
            return validate_agent_decision(state, self.player_id, decision)
        except (LlmProviderError, ValueError) as exc:
            self.last_source = "error"
            self.last_error = str(exc)[:180]
            raise LlmProviderError(f"Online streamed speech failed for {self.player_id}.") from exc

    async def _complete_content(
        self,
        request: ChatCompletionRequest,
        *,
        stream_speech: bool,
        on_speech_delta: SpeechStreamCallback | None,
    ) -> str:
        """返回完整模型文本；需要时同步抽取 speech 字段给调用方预览。"""
        if not stream_speech or on_speech_delta is None:
            response = await self.provider.complete(request)
            return response.content

        content_parts: list[str] = []
        extractor = _JsonStringFieldStream("speech")
        last_published_speech = ""
        try:
            async for chunk in self.provider.stream_complete(request):
                content_parts.append(chunk)
                speech = extractor.feed(chunk)
                if speech is not None and _should_publish_speech_preview(
                    speech,
                    last_published_speech,
                ):
                    await _maybe_await(on_speech_delta(self.player_id, speech))
                    last_published_speech = speech
        except LlmProviderError:
            if content_parts:
                raise
            response = await self.provider.complete(request)
            return response.content

        content = "".join(content_parts)
        if not content.strip():
            raise LlmProviderError("Online agent stream response content is empty.")
        return content

    async def _complete_streamed_speech_text(
        self,
        request: ChatCompletionRequest,
        *,
        on_speech_delta: SpeechStreamCallback | None,
        timeout_seconds: int = SPEECH_STREAM_SOFT_TIMEOUT_SECONDS,
    ) -> str:
        """返回公开发言正文；即便上游只给整段响应，也按小段推给前端。"""
        if on_speech_delta is None:
            response = await self.provider.complete(request)
            return _clean_speech_text(response.content)

        content_parts: list[str] = []
        last_published_speech = ""
        try:
            async with asyncio.timeout(max(1, timeout_seconds)):
                async for chunk in self.provider.stream_complete(request):
                    for piece in _split_stream_chunk(chunk):
                        content_parts.append(piece)
                        speech = _clean_speech_text("".join(content_parts), allow_partial=True)
                        if speech and _should_publish_speech_preview(speech, last_published_speech):
                            await _maybe_await(on_speech_delta(self.player_id, speech))
                            last_published_speech = speech
                        if len(speech) >= SPEECH_MAX_CHARS:
                            if speech != last_published_speech:
                                await _maybe_await(on_speech_delta(self.player_id, speech))
                            return speech
                        if len(chunk) > 16:
                            await asyncio.sleep(0.015)
        except TimeoutError:
            speech = _clean_speech_text("".join(content_parts))
            if speech:
                if speech != last_published_speech:
                    await _maybe_await(on_speech_delta(self.player_id, speech))
                return speech
            raise LlmProviderError("Online streamed speech response timed out before content.")
        except LlmProviderError:
            speech = _clean_speech_text("".join(content_parts))
            if speech:
                if speech != last_published_speech:
                    await _maybe_await(on_speech_delta(self.player_id, speech))
                return speech
            response = await self.provider.complete(request)
            speech = _clean_speech_text(response.content)
            await _publish_speech_progressively(self.player_id, speech, on_speech_delta)
            return speech

        speech = _clean_speech_text("".join(content_parts))
        if not speech:
            raise LlmProviderError("Online streamed speech response content is empty.")
        if speech != last_published_speech:
            await _maybe_await(on_speech_delta(self.player_id, speech))
        return speech


def _parse_json_object(content: str) -> object:
    """解析模型返回的 JSON；允许从包裹文本中修复提取 JSON 对象。"""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise
        return json.loads(match.group(0))


def _clean_speech_text(content: str, *, allow_partial: bool = False) -> str:
    """把纯文本发言裁剪成可展示、可落盘的正文。"""
    text = content.strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    if not allow_partial:
        text = re.sub(r"^(?:发言|speech)\s*[:：]\s*", "", text, flags=re.IGNORECASE).strip()
    return text[:SPEECH_MAX_CHARS]


def _split_stream_chunk(chunk: str) -> list[str]:
    """把可能被上游一次性返回的大块文本拆成更细的预览片段。"""
    if len(chunk) <= 8:
        return [chunk]
    return [chunk[index : index + 8] for index in range(0, len(chunk), 8)]


async def _publish_speech_progressively(
    player_id: str,
    speech: str,
    on_speech_delta: SpeechStreamCallback,
) -> None:
    """上游无法流式返回时，把最终发言按小段补发给前端。"""
    last_published = ""
    for index in range(8, len(speech) + 8, 8):
        current = speech[:index]
        if current == last_published:
            continue
        await _maybe_await(on_speech_delta(player_id, current))
        last_published = current
        await asyncio.sleep(0.015)


class _JsonStringFieldStream:
    """从增量 JSON 文本中提取某个字符串字段的当前值。"""

    def __init__(self, field_name: str) -> None:
        self._field_name = field_name
        self._buffer = ""
        self._last_value = ""

    def feed(self, chunk: str) -> str | None:
        self._buffer += chunk
        value = _extract_json_string_field(self._buffer, self._field_name)
        if value is None or value == self._last_value:
            return None
        self._last_value = value
        return value


def _extract_json_string_field(buffer: str, field_name: str) -> str | None:
    """从可能尚未完成的 JSON 对象文本中解析字符串字段片段。"""
    match = re.search(rf'"{re.escape(field_name)}"\s*:\s*"', buffer)
    if match is None:
        return None

    raw_chars: list[str] = []
    index = match.end()
    escaped = False
    while index < len(buffer):
        char = buffer[index]
        if escaped:
            raw_chars.append(f"\\{char}")
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return _decode_json_string_fragment("".join(raw_chars))
        else:
            raw_chars.append(char)
        index += 1

    return _decode_json_string_fragment("".join(raw_chars))


def _decode_json_string_fragment(raw: str) -> str | None:
    """尽量解码 JSON 字符串片段，末尾半截 unicode escape 会先被裁掉。"""
    candidates = [raw, re.sub(r"\\u[0-9a-fA-F]{0,3}$", "", raw)]
    for candidate in candidates:
        try:
            value: Any = json.loads(f'"{candidate}"')
        except json.JSONDecodeError:
            continue
        if isinstance(value, str):
            return value
    return None


async def _maybe_await(value: Awaitable[None] | None) -> None:
    if isawaitable(value):
        await value


def _should_publish_speech_preview(current: str, previous: str) -> bool:
    """降低前端刷新频率，同时保留逐段出现的发言感。"""
    if not previous:
        return bool(current.strip())
    if len(current) - len(previous) >= 12:
        return True
    return current.endswith(("。", "！", "？", "；", ".", "!", "?", ";", "\n"))
