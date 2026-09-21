"""Claude provider — streams text, loops on tool_use, supports thinking + memory."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from asgiref.sync import sync_to_async

from apps.ai.catalog import (
    THINKING_ADAPTIVE,
    THINKING_BUDGET,
    get_model,
    resolve_effort,
    thinking_style,
)
from apps.ai.providers._config import client_kwargs
from apps.ai.types import (
    CitationEvent,
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

log = logging.getLogger(__name__)


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        kw = client_kwargs()
        if base_url:
            self._client = AsyncAnthropic(api_key=api_key, base_url=base_url, **kw)
        else:
            self._client = AsyncAnthropic(api_key=api_key, **kw)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import is_mock_mode

        if is_mock_mode():
            from apps.ai.providers._mock import mock_run

            async for ev in mock_run("claude"):
                yield ev
            return

        system_blocks = _system_blocks(req.system, cache=req.cache_system)
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        messages = _maybe_cache_last_message(messages, cache=req.cache_last_message)

        total_in = total_out = total_cached = total_cache_write = 0
        memory_handler = _make_memory_handler(req.memory_dir)
        tool_rounds = 0
        tools_enabled = True

        try:
            while True:
                tools_list: list[dict] = list(req.tools) if tools_enabled else []
                if req.memory_dir and tools_enabled:
                    tools_list.append({"type": "memory_20250818", "name": "memory"})
                stream_kwargs: dict = dict(
                    model=req.model,
                    system=system_blocks,
                    messages=messages,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                )
                if tools_list:
                    stream_kwargs["tools"] = tools_list
                _apply_thinking(stream_kwargs, req)

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
                        elif etype == "citation":
                            yield _citation_event(getattr(event, "citation", None))
                    final = await stream.get_final_message()

                u = final.usage
                # Anthropic reports input_tokens (full-rate), cache_read, and
                # cache_creation as DISJOINT buckets. input_tokens here is the
                # TOTAL prompt (sum of all three) to match cost.py's convention;
                # cache_read/cache_write are the cheap-read and write-premium subsets.
                read = getattr(u, "cache_read_input_tokens", 0) or 0
                write = getattr(u, "cache_creation_input_tokens", 0) or 0
                total_in += (getattr(u, "input_tokens", 0) or 0) + read + write
                total_out += getattr(u, "output_tokens", 0) or 0
                total_cached += read
                total_cache_write += write

                # Emit the running total after every completed round. Each tool
                # round re-sends the whole conversation and is genuinely billed
                # upstream, so the consumer must see accrued usage even when a
                # later round errors (ErrorEvent replaces any final yield) or the
                # user stops the stream (the generator is closed before it could
                # emit). Cumulative snapshots keep the consumer's dict.update()
                # semantics correct — the last event seen is the true total.
                yield UsageEvent(
                    usage=TokenUsage(
                        input_tokens=total_in,
                        output_tokens=total_out,
                        cached_tokens=total_cached,
                        cache_write_tokens=total_cache_write,
                    )
                )

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
                    # Offload tool dispatch (sync, ORM-touching) OFF the loop
                    # thread; running sync ORM here trips @async_unsafe on reconnect.
                    outcome = await sync_to_async(_dispatch_tool, thread_sensitive=True)(
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

                tool_rounds += 1
                if req.max_tool_iterations and tool_rounds >= req.max_tool_iterations:
                    # Ceiling reached: next pass runs tool-less so the model must
                    # conclude (the `not tools_list` guard then breaks the loop).
                    tools_enabled = False

            # The final round's cumulative UsageEvent was already emitted inside
            # the loop; only the completion marker remains.
            yield DoneEvent()
        except Exception as exc:
            # ErrorEvent reaches the consumer, but the Celery task still
            # "succeeds" — log here or the traceback is lost server-side.
            log.exception("provider stream failed")
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _apply_thinking(kwargs: dict, req: RunRequest) -> None:
    """Attach thinking / effort in the shape ``req.model`` accepts.

    The adaptive rows take ``{"type": "adaptive"}`` plus ``output_config.effort``
    and 400 on ``budget_tokens``; the budget rows take only ``budget_tokens`` and
    400 on both adaptive and effort. ``display`` is pinned to "summarized" because
    the API default is "omitted", which streams thinking blocks whose text is
    empty — a blank thinking panel in the UI.

    Turning thinking OFF on an adaptive row has to be explicit: those models think
    by default, so omitting the parameter leaves it on and still bills for it. The
    off switch sends ``{"type": "disabled"}`` and drops the effort hint with it,
    because that pairing is rejected above effort "high" and effort only shapes
    thinking depth anyway. Where the row cannot disable thinking at all, the
    parameter is omitted and the run thinks — the honest outcome, not a 400.
    """
    style = thinking_style("claude", req.model)
    info = get_model("claude", req.model)
    if req.enable_thinking:
        if style == THINKING_ADAPTIVE:
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        elif style == THINKING_BUDGET and req.thinking_budget > 0:
            # budget_tokens must be >= 1024 AND strictly below max_tokens. When
            # max_tokens leaves no room for the floor, drop thinking rather than
            # send a request the API rejects outright.
            budget = min(req.thinking_budget, req.max_tokens - 1)
            if budget >= 1024:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
    elif style == THINKING_ADAPTIVE and (info is None or info.thinking_can_disable):
        kwargs["thinking"] = {"type": "disabled"}
        return
    effort = resolve_effort("claude", req.model, req.effort)
    if effort:
        kwargs["output_config"] = {"effort": effort}


def _citation_event(citation: object) -> CitationEvent:
    """Normalize one Anthropic citation into a CitationEvent.

    Every attribute is read with a default: a document citation
    (char/page/content-block location) carries `document_title` and NO
    `source`/`title`, so a direct attribute read would raise inside the stream
    loop — where the exception is swallowed into an ErrorEvent.
    """
    return CitationEvent(
        location=str(getattr(citation, "type", "") or ""),
        # search_result → source; web search → url; document → neither.
        source=str(getattr(citation, "source", "") or getattr(citation, "url", "") or ""),
        title=str(getattr(citation, "title", "") or getattr(citation, "document_title", "") or ""),
        cited_text=str(getattr(citation, "cited_text", "") or ""),
    )


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
