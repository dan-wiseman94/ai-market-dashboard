"""Shared mock-event translation for providers (active when MOCK_EXTERNAL=true).

ClaudeProvider and OpenAIProvider both translate the deterministic
``MockAIEvent`` stream into the normalized ``RunEvent`` union. The
thinking / tool_call / tool_result branches only ever fire for Claude
scenarios — the openai/local services never map to handlers that emit
those event types (see apps.core.mocks.scenarios) — so one shared mapping
is behavior-preserving for every provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    TextDelta,
    ThinkingDeltaEvent,
    TokenUsage,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


async def mock_run(service: str) -> AsyncIterator[RunEvent]:
    """Yield normalized RunEvents for the active mock scenario's ``service`` stream."""
    from apps.core.mocks import current_scenario
    from apps.core.mocks.providers import get_ai_stream_for_scenario

    try:
        events = get_ai_stream_for_scenario(current_scenario(), service)
    except Exception as exc:
        yield ErrorEvent(message=str(exc))
        return
    for ev in events:
        if ev.type == "text_delta":
            yield TextDelta(text=ev.text)
        elif ev.type == "thinking_delta":
            yield ThinkingDeltaEvent(text=ev.text)
        elif ev.type == "tool_call":
            yield ToolCallEvent(tool_use_id="mock-1", name=ev.text, input={"ticker": "AAPL"})
        elif ev.type == "tool_result":
            yield ToolResultEvent(tool_use_id="mock-1", result={"last": 175.0}, ok=True)
        elif ev.type == "usage":
            yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))
        elif ev.type == "error":
            yield ErrorEvent(message=ev.text or "mock error")
            return
        elif ev.type == "done":
            yield DoneEvent()
            return
    yield DoneEvent()
