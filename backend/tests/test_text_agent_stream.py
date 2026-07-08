"""Tests for streamed public speech completion."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.agents.text_agent import SPEECH_MAX_CHARS, TextAgent
from app.llm.base import ChatCompletionRequest


class LongSpeechProvider:
    """Provider that returns more text than one public speech may use."""

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        yield "a" * (SPEECH_MAX_CHARS + 80)
        while True:
            await asyncio.sleep(1)


class HangingSpeechProvider:
    """Provider that starts a response but never sends a final SSE marker."""

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        yield "partial speech"
        while True:
            await asyncio.sleep(1)


def test_streamed_speech_stops_at_public_speech_limit() -> None:
    """Long-running speech streams should be cut once the public speech limit is reached."""

    async def scenario() -> None:
        agent = TextAgent("p2", player_index=2)
        agent.provider = LongSpeechProvider()  # type: ignore[assignment]
        deltas: list[str] = []

        speech = await agent._complete_streamed_speech_text(
            _request(),
            on_speech_delta=lambda _player_id, text: deltas.append(text),
            timeout_seconds=5,
        )

        assert len(speech) == SPEECH_MAX_CHARS
        assert deltas[-1] == speech

    asyncio.run(scenario())


def test_streamed_speech_commits_partial_content_on_soft_timeout() -> None:
    """A stream that never closes should still commit useful partial speech."""

    async def scenario() -> None:
        agent = TextAgent("p2", player_index=2)
        agent.provider = HangingSpeechProvider()  # type: ignore[assignment]
        deltas: list[str] = []

        speech = await agent._complete_streamed_speech_text(
            _request(),
            on_speech_delta=lambda _player_id, text: deltas.append(text),
            timeout_seconds=1,
        )

        assert speech == "partial speech"
        assert deltas[-1] == speech

    asyncio.run(scenario())


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest(messages=[], model="test-model", temperature=0.1)
