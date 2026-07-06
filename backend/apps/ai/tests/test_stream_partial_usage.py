"""Providers must surface usage for completed tool rounds even when a later
round errors — each round is genuinely billed upstream, so the accrued spend
must reach the consumer before the ErrorEvent (a single end-of-run UsageEvent
would be lost when the loop aborts)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.ai.tools import Toolset, ToolSpec
from apps.ai.types import ChatMessage, ErrorEvent, RunRequest, UsageEvent


def _drain(gen):
    async def run():
        return [evt async for evt in gen]

    return asyncio.run(run())


def _claude_stream(final):
    cm = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = cm
    ctx.__aexit__.return_value = False

    async def aiter(self):
        for block in final.content:
            if getattr(block, "type", None) == "text":
                yield MagicMock(type="text", text=block.text)

    cm.__aiter__ = aiter
    cm.get_final_message = AsyncMock(return_value=final)
    return ctx


def test_claude_yields_usage_for_completed_rounds_before_error() -> None:
    from apps.ai.providers.claude import ClaudeProvider

    ts = Toolset()
    ts.register(
        ToolSpec(
            name="get_quote",
            description="",
            input_schema={"type": "object"},
            fn=lambda **_: {"AAPL": {"last": 180.0}},
        )
    )

    tool_block = MagicMock(type="tool_use", id="tu_1", input={"ticker": "AAPL"})
    tool_block.name = "get_quote"
    first = MagicMock(
        stop_reason="tool_use",
        content=[tool_block],
        usage=MagicMock(
            input_tokens=50,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )

    with (
        patch("apps.ai.providers.claude.AsyncAnthropic") as ac,
        patch("apps.ai.providers.claude._resolve_toolset", return_value=ts),
    ):
        client = ac.return_value
        # Round 1 completes (tool_use); round 2's stream construction blows up.
        client.messages.stream = MagicMock(
            side_effect=[_claude_stream(first), RuntimeError("boom")]
        )
        provider = ClaudeProvider(api_key="x")
        req = RunRequest(
            model="claude-opus-4-8",
            system="",
            messages=[ChatMessage(role="user", content="hi")],
            tools=ts.anthropic_tools(),
        )
        events = _drain(provider.run(req))

    kinds = [type(e).__name__ for e in events]
    assert kinds[-1] == "ErrorEvent"
    usage_events = [e for e in events if isinstance(e, UsageEvent)]
    assert len(usage_events) == 1  # round 1 completed; round 2 never did
    assert usage_events[0].usage.input_tokens == 50
    assert usage_events[0].usage.output_tokens == 5
    # The usage must precede the error so the consumer books it.
    assert kinds.index("UsageEvent") < kinds.index("ErrorEvent")


class _ToolCallStream:
    """One streamed round finishing with a tool_call and usage 50/5."""

    def __aiter__(self):
        async def gen():
            c = MagicMock()
            ch = MagicMock()
            ch.delta.content = None
            tc = MagicMock()
            tc.index = 0
            tc.id = "call_1"
            tc.function.name = "get_quote"
            tc.function.arguments = '{"ticker": "AAPL"}'
            ch.delta.tool_calls = [tc]
            ch.finish_reason = "tool_calls"
            c.choices = [ch]
            c.usage = MagicMock(
                prompt_tokens=50,
                completion_tokens=5,
                prompt_tokens_details=MagicMock(cached_tokens=0),
            )
            yield c

        return gen()


def test_openai_yields_usage_for_completed_rounds_before_error() -> None:
    from apps.ai.providers.openai import OpenAIProvider

    calls = {"n": 0}

    async def fake_create(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _ToolCallStream()
        raise RuntimeError("boom")

    fake = MagicMock()
    fake.chat.completions.create = fake_create
    fake_toolset = MagicMock()
    fake_toolset.run.return_value = {"ok": True, "result": {"last": 200}}

    with (
        patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake),
        patch("apps.ai.providers.openai._resolve_toolset", return_value=fake_toolset),
    ):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="",
            messages=[ChatMessage(role="user", content="quote AAPL")],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "get_quote", "description": "", "parameters": {}},
                }
            ],
        )
        events = _drain(provider.run(req))

    kinds = [type(e).__name__ for e in events]
    assert isinstance(events[-1], ErrorEvent)
    usage_events = [e for e in events if isinstance(e, UsageEvent)]
    assert len(usage_events) == 1
    assert usage_events[0].usage.input_tokens == 50
    assert usage_events[0].usage.output_tokens == 5
    assert kinds.index("UsageEvent") < kinds.index("ErrorEvent")
