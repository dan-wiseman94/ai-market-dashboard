"""Drive a provider stream into mutable result containers.

Split out of ``tasks.py``; re-exported there as ``apps.threads.tasks._build_stream_runner``.

Broadcasts go through ``apps.threads.tasks._broadcast_async`` (resolved lazily at
call time) so tests that patch that attribute on the ``tasks`` module still apply
to the running ``drive()`` loop.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import asdict
from typing import Any

from apps.ai.providers.base import Provider
from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunRequest,
    TextDelta,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


def _build_stream_runner(
    buffer: list[str],
    usage_dict: dict[str, int],
    err_container: list[str],
    tool_events: list[dict],
    provider: Provider,
    req: RunRequest,
    thread_id: int,
    assistant_id: int,
    should_stop: Callable[[], bool] = lambda: False,
) -> Callable[[], Coroutine[Any, Any, None]]:
    """Return a drive() coroutine that reads from the provider stream.

    Mutates the mutable containers in-place:
      buffer       — text delta strings are appended.
      usage_dict   — updated with input_tokens / output_tokens / cached_tokens.
      err_container — first element set to the error string on provider error.
      tool_events  — tool_call / tool_result event dicts appended in order.

    `should_stop` is polled before each event; when it returns True the loop breaks
    and the provider generator is closed, aborting the upstream stream.
    """
    # Resolve the broadcaster off the tasks module so test patches of
    # apps.threads.tasks._broadcast_async take effect inside drive().
    from apps.threads import tasks

    async def emit(payload: dict) -> None:
        await tasks._broadcast_async(thread_id, payload)

    async def drive() -> None:
        gen = provider.run(req)
        try:
            async for evt in gen:
                if should_stop():
                    break
                if isinstance(evt, TextDelta):
                    buffer.append(evt.text)
                    await emit(
                        {"event": "text_delta", "message_id": assistant_id, "text": evt.text}
                    )
                elif isinstance(evt, ThinkingDeltaEvent):
                    await emit(
                        {"event": "thinking_delta", "message_id": assistant_id, "text": evt.text}
                    )
                elif isinstance(evt, ToolCallEvent):
                    tool_events.append(
                        {
                            "kind": "call",
                            "tool_use_id": evt.tool_use_id,
                            "name": evt.name,
                            "input": evt.input,
                        }
                    )
                    await emit(
                        {
                            "event": "tool_call",
                            "message_id": assistant_id,
                            "tool_use_id": evt.tool_use_id,
                            "name": evt.name,
                            "input": evt.input,
                        }
                    )
                elif isinstance(evt, ToolResultEvent):
                    tool_events.append(
                        {
                            "kind": "result",
                            "tool_use_id": evt.tool_use_id,
                            "ok": evt.ok,
                            "result": evt.result,
                            "error": evt.error,
                            "latency_ms": evt.latency_ms,
                        }
                    )
                    await emit(
                        {
                            "event": "tool_result",
                            "message_id": assistant_id,
                            "tool_use_id": evt.tool_use_id,
                            "ok": evt.ok,
                            "latency_ms": evt.latency_ms,
                        }
                    )
                elif isinstance(evt, UsageEvent):
                    usage_dict.update(asdict(evt.usage))
                elif isinstance(evt, ErrorEvent):
                    err_container.append(evt.message)
                elif isinstance(evt, DoneEvent):
                    return
        finally:
            # Close the generator so a break aborts the upstream stream. Providers
            # are async generators (have aclose); guard for plain async iterators.
            aclose = getattr(gen, "aclose", None)
            if aclose is not None:
                await aclose()

    return drive
