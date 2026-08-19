"""A provider stream failure must leave a server-side traceback — the ErrorEvent
reaches the consumer but the Celery task still "succeeds", so log.exception is
the only trace of a code bug inside the streaming loop."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

from apps.ai.types import ChatMessage, ErrorEvent, RunRequest


def _drain(gen):
    async def run():
        return [evt async for evt in gen]

    return asyncio.run(run())


def test_claude_stream_failure_logs_exception_with_traceback(caplog) -> None:
    from apps.ai.providers.claude import ClaudeProvider

    with patch("apps.ai.providers.claude.AsyncAnthropic") as ac:
        ac.return_value.messages.stream = MagicMock(side_effect=RuntimeError("boom"))
        provider = ClaudeProvider(api_key="x")
        req = RunRequest(
            model="claude-opus-4-8",
            system="",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with caplog.at_level(logging.ERROR, logger="apps.ai.providers.claude"):
            events = _drain(provider.run(req))

    assert isinstance(events[-1], ErrorEvent)
    records = [r for r in caplog.records if r.message == "provider stream failed"]
    assert len(records) == 1
    assert records[0].exc_info is not None  # full traceback, not just the message


def test_openai_stream_failure_logs_exception_with_traceback(caplog) -> None:
    from apps.ai.providers.openai import OpenAIProvider

    async def fake_create(**_kwargs):
        raise RuntimeError("boom")

    fake = MagicMock()
    fake.chat.completions.create = fake_create

    with patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="",
            messages=[ChatMessage(role="user", content="hi")],
        )
        with caplog.at_level(logging.ERROR, logger="apps.ai.providers.openai"):
            events = _drain(provider.run(req))

    assert isinstance(events[-1], ErrorEvent)
    records = [r for r in caplog.records if r.message == "openai provider stream failed"]
    assert len(records) == 1
    assert records[0].exc_info is not None  # full traceback, not just the message
