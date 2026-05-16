"""When run_ai_on_message receives ToolCall/ToolResult events, it must persist
ToolCall rows on the assistant Message."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread, ToolCall


@pytest.fixture
def thread_and_message(db):
    cfg = ProviderConfig.objects.create(
        provider="claude",
        enabled=True,
        default_model="claude-opus-4-7",
    )
    cfg.api_key = "sk-test"
    cfg.save()
    profile = TradingProfile.objects.create(
        name="p",
        style="s",
        default_provider="claude",
        default_model="claude-opus-4-7",
        enable_tools=True,
    )
    thread = Thread.objects.create(kind="consult", profile=profile)
    user_msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": "what's AAPL?"},
        status="done",
    )
    return thread, user_msg


def test_tool_call_events_persist_toolcall_rows(db, thread_and_message) -> None:
    from apps.ai.types import (
        DoneEvent,
        TextDelta,
        TokenUsage,
        ToolCallEvent,
        ToolResultEvent,
        UsageEvent,
    )
    from apps.threads.tasks import run_ai_on_message

    thread, user_msg = thread_and_message

    async def fake_provider_run(self, req):
        yield ToolCallEvent(tool_use_id="tu_1", name="get_quote", input={"ticker": "AAPL"})
        yield ToolResultEvent(
            tool_use_id="tu_1",
            ok=True,
            result={"AAPL": {"last": 180.0}},
            latency_ms=12,
        )
        yield TextDelta(text="AAPL 180")
        yield UsageEvent(usage=TokenUsage(input_tokens=5, output_tokens=3, cached_tokens=0))
        yield DoneEvent()

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_provider_run):
        run_ai_on_message(thread_id=thread.id, user_message_id=user_msg.id)

    assistant = Message.objects.filter(thread=thread, role="assistant", status="done").first()
    assert assistant is not None
    tcs = list(ToolCall.objects.filter(message=assistant))
    assert len(tcs) == 1
    tc = tcs[0]
    assert tc.tool_name == "get_quote"
    assert tc.tool_input == {"ticker": "AAPL"}
    assert tc.ok is True
    assert tc.tool_output == {"AAPL": {"last": 180.0}}
    assert tc.latency_ms == 12


def test_no_tool_calls_persists_no_rows(db, thread_and_message) -> None:
    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent
    from apps.threads.tasks import run_ai_on_message

    thread, user_msg = thread_and_message

    async def fake_provider_run(self, req):
        yield TextDelta(text="just text")
        yield UsageEvent(usage=TokenUsage(input_tokens=2, output_tokens=2, cached_tokens=0))
        yield DoneEvent()

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_provider_run):
        run_ai_on_message(thread_id=thread.id, user_message_id=user_msg.id)

    assistant = Message.objects.filter(thread=thread, role="assistant", status="done").first()
    assert assistant is not None
    assert ToolCall.objects.filter(message=assistant).count() == 0
