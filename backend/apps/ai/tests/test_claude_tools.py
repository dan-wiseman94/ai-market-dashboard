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


def _req(
    tools: list[dict],
    *,
    budget: int = 0,
    thinking: bool = False,
    effort: str = "",
    model: str = "claude-opus-4-8",
) -> RunRequest:
    return RunRequest(
        model=model,
        system="",
        messages=[ChatMessage(role="user", content="hi")],
        tools=tools,
        enable_thinking=thinking,
        effort=effort,
        thinking_budget=budget,
    )


def _stream_kwargs(req: RunRequest) -> dict:
    """Run `req` against a mocked SDK and return the kwargs it streamed with."""
    from apps.ai.providers.claude import ClaudeProvider

    final = MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text="ok")],
        usage=MagicMock(input_tokens=1, output_tokens=1, cache_read_input_tokens=0),
    )
    with patch("apps.ai.providers.claude.AsyncAnthropic") as ac:
        stream_mock = MagicMock(return_value=_make_stream(final))
        ac.return_value.messages.stream = stream_mock
        asyncio.run(_drain(ClaudeProvider(api_key="x").run(req)))
    return stream_mock.call_args.kwargs


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


def test_adaptive_model_sends_adaptive_thinking_and_effort() -> None:
    kwargs = _stream_kwargs(_req(tools=[], thinking=True, effort="max", budget=8000))

    # budget_tokens is a 400 on this row; display must be explicit or the API
    # defaults to "omitted" and streams empty thinking text.
    assert kwargs.get("thinking") == {"type": "adaptive", "display": "summarized"}
    assert kwargs.get("output_config") == {"effort": "max"}


def test_effort_steps_down_to_a_level_the_model_exposes() -> None:
    # Thinking on, because the effort hint only rides along with it.
    kwargs = _stream_kwargs(
        _req(tools=[], thinking=True, effort="xhigh", model="claude-sonnet-4-6")
    )

    assert kwargs.get("output_config") == {"effort": "high"}


def test_effort_is_dropped_when_thinking_is_switched_off() -> None:
    # An adaptive row thinks unless told not to, so "off" must be sent. Effort goes
    # with it: the pairing is rejected above "high" and effort only shapes thinking.
    kwargs = _stream_kwargs(_req(tools=[], effort="low"))

    assert kwargs["thinking"] == {"type": "disabled"}
    assert "output_config" not in kwargs


def test_budget_model_keeps_the_budget_shape_clamped_below_max_tokens() -> None:
    req = _req(tools=[], thinking=True, budget=99_000, model="claude-haiku-4-5-20251001")
    kwargs = _stream_kwargs(req)

    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": req.max_tokens - 1}
    # This row rejects output_config.effort outright.
    assert "output_config" not in kwargs


def test_budget_model_drops_thinking_when_max_tokens_leaves_no_room() -> None:
    # budget_tokens has a 1024 floor and must stay below max_tokens; when both
    # can't hold, omitting thinking beats a request the API rejects.
    req = _req(tools=[], thinking=True, budget=2000, model="claude-haiku-4-5-20251001")
    req.max_tokens = 512
    kwargs = _stream_kwargs(req)

    assert "thinking" not in kwargs


def test_budget_model_sends_no_effort_even_when_requested() -> None:
    kwargs = _stream_kwargs(_req(tools=[], effort="max", model="claude-haiku-4-5-20251001"))

    assert "output_config" not in kwargs


def test_thinking_disabled_sends_disabled_rather_than_omitting() -> None:
    # Omitting the parameter would leave adaptive thinking on and still bill for it.
    kwargs = _stream_kwargs(_req(tools=[], budget=8000))

    assert kwargs["thinking"] == {"type": "disabled"}
