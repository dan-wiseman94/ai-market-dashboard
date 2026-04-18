"""Claude provider — streams via anthropic SDK."""
from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunRequest,
    TextDelta,
    TokenUsage,
    UsageEvent,
)


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)  # type: ignore[arg-type]

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import is_mock_mode
        if is_mock_mode():
            yield TextDelta(text="Mocked ")
            yield TextDelta(text="response")
            yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))
            yield DoneEvent()
            return

        system_blocks = _system_blocks(req.system, cache=req.cache_system)
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        messages = _maybe_cache_last_message(messages, cache=req.cache_last_message)

        try:
            async with self._client.messages.stream(
                model=req.model,
                system=system_blocks,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(text=event.text)
                final = await stream.get_final_message()
            u = final.usage
            yield UsageEvent(usage=TokenUsage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            ))
            yield DoneEvent()
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _system_blocks(system: str, *, cache: bool) -> list[dict]:
    block: dict = {"type": "text", "text": system}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def _maybe_cache_last_message(messages: list[dict], *, cache: bool) -> list[dict]:
    """Attach cache_control to the final text block of the last message.

    Rebuilds the last message with `content` as a single text-block list so we
    can hang cache_control off it. Earlier messages are unchanged — Anthropic
    caches everything *before* the breakpoint on hit.
    """
    if not cache or not messages:
        return messages
    out = [dict(m) for m in messages]
    last = out[-1]
    text = last["content"] if isinstance(last["content"], str) else ""
    last["content"] = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    return out
