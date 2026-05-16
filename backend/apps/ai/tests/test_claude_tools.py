"""Claude provider tool-use loop + thinking, with SDK mocked."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from apps.ai.tools import Toolset, ToolSpec
from apps.ai.types import (
    ChatMessage,
    RunRequest,
    TextDelta,
    ToolCallEvent,
    ToolResultEvent,
)


def _req(tools: list[dict], *, budget: int = 0) -> RunRequest:
    return RunRequest(
        model="claude-opus-4-7",
        system="",
        messages=[ChatMessage(role="user", content="hi")],
        tools=tools,
        thinking_budget=budget,
    )


def _make_stream(final):
    cm = MagicMock()
    async_ctx = AsyncMock()
    async_ctx.__aenter__.return_value = cm
    async_ctx.__aexit__.return_value = False

    async def aiter(self):
        for block in final.content:
            if getattr(block, "type", None) == "text":
                yield MagicMock(type="text", text=block.text)

    cm.__aiter__ = aiter
    cm.get_final_message = AsyncMock(return_value=final)
    return async_ctx


async def _drain(gen):
    events = []
    async for evt in gen:
        events.append(evt)
    return events


def test_tool_use_loops_and_yields_events() -> None:
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
    tool_block.name = "get_quote"  # `name` is MagicMock-reserved; set explicitly.
    first = MagicMock(
        stop_reason="tool_use",
        content=[tool_block],
        usage=MagicMock(input_tokens=5, output_tokens=2, cache_read_input_tokens=0),
    )
    second = MagicMock(
        stop_reason="end_turn",
        content=[
            MagicMock(
                type="text",
                text="AAPL at 180",
            )
        ],
        usage=MagicMock(input_tokens=3, output_tokens=4, cache_read_input_tokens=0),
    )

    with (
        patch("apps.ai.providers.claude.AsyncAnthropic") as ac,
        patch("apps.ai.providers.claude._resolve_toolset", return_value=ts),
    ):
        client = ac.return_value
        client.messages.stream = MagicMock(
            side_effect=[
                _make_stream(first),
                _make_stream(second),
            ]
        )

        provider = ClaudeProvider(api_key="x")
        events = asyncio.run(_drain(provider.run(_req(ts.anthropic_tools()))))

    kinds = [type(e).__name__ for e in events]
    assert kinds.count("ToolCallEvent") == 1
    assert kinds.count("ToolResultEvent") == 1
    assert any(isinstance(e, TextDelta) for e in events)
    assert kinds[-2:] == ["UsageEvent", "DoneEvent"]

    tc_evt = next(e for e in events if isinstance(e, ToolCallEvent))
    assert tc_evt.name == "get_quote"
    assert tc_evt.input == {"ticker": "AAPL"}
    tr_evt = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tr_evt.ok is True


def test_no_tools_path_unchanged() -> None:
    from apps.ai.providers.claude import ClaudeProvider

    final = MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text="hi")],
        usage=MagicMock(input_tokens=2, output_tokens=1, cache_read_input_tokens=0),
    )

    with patch("apps.ai.providers.claude.AsyncAnthropic") as ac:
        client = ac.return_value
        client.messages.stream = MagicMock(return_value=_make_stream(final))
        provider = ClaudeProvider(api_key="x")
        events = asyncio.run(_drain(provider.run(_req(tools=[]))))

    assert any(isinstance(e, TextDelta) for e in events)
    assert not any(isinstance(e, ToolCallEvent) for e in events)


def test_thinking_budget_positive_passes_thinking_kwarg() -> None:
    from apps.ai.providers.claude import ClaudeProvider

    final = MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text="ok")],
        usage=MagicMock(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
    )

    with patch("apps.ai.providers.claude.AsyncAnthropic") as ac:
        client = ac.return_value
        stream_mock = MagicMock(return_value=_make_stream(final))
        client.messages.stream = stream_mock
        provider = ClaudeProvider(api_key="x")
        asyncio.run(_drain(provider.run(_req(tools=[], budget=8000))))

    kwargs = stream_mock.call_args.kwargs
    assert kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 8000}


def test_thinking_budget_zero_omits_thinking_kwarg() -> None:
    from apps.ai.providers.claude import ClaudeProvider

    final = MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text="ok")],
        usage=MagicMock(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
    )

    with patch("apps.ai.providers.claude.AsyncAnthropic") as ac:
        client = ac.return_value
        stream_mock = MagicMock(return_value=_make_stream(final))
        client.messages.stream = stream_mock
        provider = ClaudeProvider(api_key="x")
        asyncio.run(_drain(provider.run(_req(tools=[], budget=0))))

    kwargs = stream_mock.call_args.kwargs
    assert "thinking" not in kwargs
