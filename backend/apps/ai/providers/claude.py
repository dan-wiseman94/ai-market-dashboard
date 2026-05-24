"""Claude provider — streams text, loops on tool_use, supports thinking + memory."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunRequest,
    TextDelta,
    ThinkingDeltaEvent,
    TokenUsage,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        if base_url:
            self._client = AsyncAnthropic(api_key=api_key, base_url=base_url)
        else:
            self._client = AsyncAnthropic(api_key=api_key)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import current_scenario, is_mock_mode
        from apps.core.mocks.providers import get_ai_stream_for_scenario

        if is_mock_mode():
            try:
                events = get_ai_stream_for_scenario(current_scenario(), "claude")
            except Exception as exc:
                yield ErrorEvent(message=str(exc))
                return
            for ev in events:
                if ev.type == "text_delta":
                    yield TextDelta(text=ev.text)
                elif ev.type == "thinking_delta":
                    yield ThinkingDeltaEvent(text=ev.text)
                elif ev.type == "tool_call":
                    yield ToolCallEvent(
                        tool_use_id="mock-1", name=ev.text, input={"ticker": "AAPL"}
                    )
                elif ev.type == "tool_result":
                    yield ToolResultEvent(tool_use_id="mock-1", result={"last": 175.0}, ok=True)
                elif ev.type == "usage":
                    yield UsageEvent(
                        usage=TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0)
                    )
                elif ev.type == "error":
                    yield ErrorEvent(message=ev.text or "mock error")
                    return
                elif ev.type == "done":
                    yield DoneEvent()
                    return
            yield DoneEvent()
            return

        system_blocks = _system_blocks(req.system, cache=req.cache_system)
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        messages = _maybe_cache_last_message(messages, cache=req.cache_last_message)

        total_in = total_out = total_cached = 0
        memory_handler = _make_memory_handler(req.memory_dir)

        try:
            while True:
                stream_kwargs: dict = dict(
                    model=req.model,
                    system=system_blocks,
                    messages=messages,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                )
                tools_list: list[dict] = list(req.tools)
                if req.memory_dir:
                    tools_list.append({"type": "memory_20250818", "name": "memory"})
                if tools_list:
                    stream_kwargs["tools"] = tools_list
                if req.thinking_budget > 0:
                    stream_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": req.thinking_budget,
                    }

                stream_ctx = (
                    self._client.beta.messages.stream(
                        **stream_kwargs,
                        betas=["context-management-2025-06-27"],
                    )
                    if req.memory_dir
                    else self._client.messages.stream(**stream_kwargs)
                )
                async with stream_ctx as stream:
                    async for event in stream:
                        etype = getattr(event, "type", None)
                        if etype == "text":
                            yield TextDelta(text=getattr(event, "text", ""))
                        elif etype == "thinking":
                            yield ThinkingDeltaEvent(text=getattr(event, "thinking", ""))
                    final = await stream.get_final_message()

                u = final.usage
                total_in += getattr(u, "input_tokens", 0) or 0
                total_out += getattr(u, "output_tokens", 0) or 0
                total_cached += getattr(u, "cache_read_input_tokens", 0) or 0

                stop = getattr(final, "stop_reason", None)
                if stop != "tool_use" or not tools_list:
                    break

                toolset = _resolve_toolset()
                tool_results: list[dict] = []
                for block in final.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    tool_input = dict(getattr(block, "input", {}) or {})
                    block_id = getattr(block, "id", "")
                    block_name = getattr(block, "name", "")
                    yield ToolCallEvent(
                        tool_use_id=block_id,
                        name=block_name,
                        input=tool_input,
                    )
                    t0 = time.perf_counter()
                    outcome = _dispatch_tool(
                        block_name, tool_input, memory_handler=memory_handler, toolset=toolset
                    )
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    yield ToolResultEvent(
                        tool_use_id=block_id,
                        ok=bool(outcome.get("ok")),
                        result=outcome.get("result"),
                        error=str(outcome.get("error", "")),
                        latency_ms=latency_ms,
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block_id,
                            "content": str(
                                outcome.get("result")
                                if outcome.get("ok")
                                else outcome.get("error"),
                            ),
                            "is_error": not outcome.get("ok"),
                        }
                    )

                messages.append(
                    {
                        "role": "assistant",
                        "content": list(final.content),  # type: ignore[arg-type]
                    }
                )
                messages.append({"role": "user", "content": tool_results})

            yield UsageEvent(
                usage=TokenUsage(
                    input_tokens=total_in,
                    output_tokens=total_out,
                    cached_tokens=total_cached,
                )
            )
            yield DoneEvent()
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _resolve_toolset():
    """Late import so tests can patch without importing market services."""
    from apps.ai.tools.registry import default_toolset

    return default_toolset()


def _make_memory_handler(memory_dir: str):
    """Build the client-side memory tool handler, or None when memory is off."""
    if not memory_dir:
        return None
    from apps.ai.memory import MemoryToolHandler

    return MemoryToolHandler(memory_dir)


def _dispatch_tool(name, tool_input, *, memory_handler, toolset) -> dict:
    """Route a tool_use to the memory handler (client-side memory tool) or the
    market toolset, keeping the streaming loop agnostic to which tool fired."""
    if name == "memory" and memory_handler is not None:
        return memory_handler.run(tool_input)
    return toolset.run(name, tool_input)


def _system_blocks(system: str, *, cache: bool) -> list[dict]:
    block: dict = {"type": "text", "text": system}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def _maybe_cache_last_message(messages: list[dict], *, cache: bool) -> list[dict]:
    """Attach cache_control to the last message's final text block."""
    if not cache or not messages:
        return messages
    out = [dict(m) for m in messages]
    last = out[-1]
    content = last["content"]
    if isinstance(content, str):
        last["content"] = [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}},
        ]
        return out
    blocks = [dict(b) for b in content]
    for block in reversed(blocks):
        if block.get("type") == "text":
            block["cache_control"] = {"type": "ephemeral"}
            last["content"] = blocks
            return out
    blocks.append({"type": "text", "text": "", "cache_control": {"type": "ephemeral"}})
    last["content"] = blocks
    return out
