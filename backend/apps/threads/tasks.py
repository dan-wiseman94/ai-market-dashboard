"""AI run Celery task — drives a provider chosen by the router."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import asdict
from decimal import Decimal
from typing import Any, cast

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import transaction

from apps.ai.citations import news_to_search_result_blocks
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap, cost_usd_for
from apps.ai.providers import get_provider
from apps.ai.providers.base import Provider
from apps.ai.router import ResolutionError, resolve_provider_and_model
from apps.ai.types import (
    ChatMessage,
    DoneEvent,
    ErrorEvent,
    RoleType,
    RunRequest,
    TextDelta,
    ThinkingDeltaEvent,
    TokenUsage,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)
from apps.secrets.models import ProviderConfig
from apps.snapshots.models import SnapshotSection
from apps.snapshots.serializer import build_image_blocks
from apps.threads.models import AIRun, Message, Thread, ToolCall
from apps.threads.stop import clear_stop, is_stop_requested

_STOP_POLL_SECONDS = 0.25  # how often the streaming loop checks the stop flag


def _broadcast(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"thread.{thread_id}",
        {"type": "thread_event", "payload": payload},
    )


async def _broadcast_async(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(
        f"thread.{thread_id}",
        {"type": "thread_event", "payload": payload},
    )


def _extract_text(m: Message) -> str:
    c = m.content or {}
    if isinstance(c, dict) and "text" in c:
        return c["text"]
    return str(c)


def _snapshot_image_ids(snapshot_id: int) -> list[int]:
    section = SnapshotSection.objects.filter(
        snapshot_id=snapshot_id, kind="image", status="done"
    ).first()
    if section is None:
        return []
    payload = section.payload or {}
    return list(payload.get("image_ids") or [])


def _snapshot_news_items(snapshot_id: int) -> list[dict]:
    section = SnapshotSection.objects.filter(
        snapshot_id=snapshot_id, kind="news", status="done"
    ).first()
    if section is None:
        return []
    payload = section.payload or {}
    return list(payload.get("items") or [])


def _message_content(
    m: Message,
    *,
    provider_name: str,
) -> str | list[dict]:
    """Return the ChatMessage content for a Message — string, or blocks if the
    message references a Snapshot with image sections. Images are attached to
    the message regardless of provider; the serializer handles provider shape.
    """
    text = _extract_text(m)
    snap_id = getattr(m, "snapshot_ref_id", None)
    if not snap_id:
        return text
    blocks: list[dict] = []
    # News as citable search_result blocks — Anthropic-only shape, so Claude only.
    if provider_name == "claude":
        news_items = _snapshot_news_items(snap_id)
        if news_items:
            blocks.extend(news_to_search_result_blocks(news_items))
    # Chart images attach for every provider; build_image_blocks picks the shape.
    image_ids = _snapshot_image_ids(snap_id)
    if image_ids:
        blocks.extend(build_image_blocks(image_ids, provider_name=provider_name))
    if not blocks:
        return text
    blocks.append({"type": "text", "text": text})
    return blocks


def _build_request(
    thread: Thread,
    user_msg: Message,
    *,
    provider_name: str = "claude",
) -> RunRequest:
    system = thread.profile.style if thread.profile else ""
    history = list(
        Message.objects.filter(
            thread=thread, role__in=["user", "assistant"], status="done"
        ).order_by("created_at")
    )
    chat_messages: list[ChatMessage] = [
        ChatMessage(
            role=cast(RoleType, m.role),
            content=_message_content(m, provider_name=provider_name),
        )
        for m in history
    ]
    if not any(m.id == user_msg.id for m in history):
        chat_messages.append(
            ChatMessage(
                role="user",
                content=_message_content(user_msg, provider_name=provider_name),
            )
        )
    # M10: opt-in tool use / thinking / memory (Claude-only; other providers ignore).
    tools: list[dict] = []
    thinking_budget = 0
    memory_dir = ""
    if thread.profile and provider_name == "claude":
        if getattr(thread.profile, "enable_tools", False):
            from apps.ai.tools.registry import default_toolset

            tools = default_toolset().anthropic_tools()
        if getattr(thread.profile, "enable_thinking", False):
            thinking_budget = int(getattr(thread.profile, "thinking_budget", 0) or 0)
        if getattr(thread.profile, "enable_memory", False):
            from apps.ai.memory import memory_dir_for_profile

            memory_dir = memory_dir_for_profile(profile_id=thread.profile.id)

    return RunRequest(
        model="",
        system=system,
        messages=chat_messages,
        cache_system=True,
        cache_last_message=len(chat_messages) > 1,
        tools=tools,
        thinking_budget=thinking_budget,
        memory_dir=memory_dir,
    )


def _fail(
    *,
    thread_id: int,
    parent_message_id: int | None,
    error: str,
    event: str = "error",
) -> Message:
    """Create a failed assistant message and broadcast a single error/cost_capped event."""
    assistant = Message.objects.create(
        thread_id=thread_id,
        role="assistant",
        content={"text": ""},
        status="failed",
        error=error,
        parent_message_id=parent_message_id,
    )
    _broadcast(thread_id, {"event": event, "message_id": assistant.id, "error": error})
    return assistant


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

    async def drive() -> None:
        gen = provider.run(req)
        try:
            async for evt in gen:
                if should_stop():
                    break
                if isinstance(evt, TextDelta):
                    buffer.append(evt.text)
                    await _broadcast_async(
                        thread_id,
                        {
                            "event": "text_delta",
                            "message_id": assistant_id,
                            "text": evt.text,
                        },
                    )
                elif isinstance(evt, ThinkingDeltaEvent):
                    await _broadcast_async(
                        thread_id,
                        {
                            "event": "thinking_delta",
                            "message_id": assistant_id,
                            "text": evt.text,
                        },
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
                    await _broadcast_async(
                        thread_id,
                        {
                            "event": "tool_call",
                            "message_id": assistant_id,
                            "tool_use_id": evt.tool_use_id,
                            "name": evt.name,
                            "input": evt.input,
                        },
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
                    await _broadcast_async(
                        thread_id,
                        {
                            "event": "tool_result",
                            "message_id": assistant_id,
                            "tool_use_id": evt.tool_use_id,
                            "ok": evt.ok,
                            "latency_ms": evt.latency_ms,
                        },
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


def _persist_tool_calls(assistant: Message, events: list[dict]) -> None:
    """Pair tool_call with tool_result events by tool_use_id; create ToolCall rows."""
    calls: dict[str, dict] = {}
    for evt in events:
        tuid = evt["tool_use_id"]
        bucket = calls.setdefault(tuid, {})
        if evt["kind"] == "call":
            bucket["name"] = evt["name"]
            bucket["input"] = evt["input"]
        else:
            bucket["ok"] = evt.get("ok", True)
            bucket["result"] = evt.get("result")
            bucket["error"] = evt.get("error", "")
            bucket["latency_ms"] = evt.get("latency_ms", 0)
    to_create = []
    for tuid, v in calls.items():
        result = v.get("result")
        # JSONField requires dict/list; wrap scalars and Nones.
        if result is None or isinstance(result, dict | list):
            output = result if isinstance(result, dict | list) else {}
        else:
            output = {"value": result}
        to_create.append(
            ToolCall(
                message=assistant,
                tool_use_id=tuid,
                tool_name=v.get("name", ""),
                tool_input=v.get("input") or {},
                tool_output=output,
                ok=v.get("ok", True),
                error=v.get("error", ""),
                latency_ms=v.get("latency_ms", 0),
            )
        )
    if to_create:
        ToolCall.objects.bulk_create(to_create)


@shared_task(name="threads.run_ai_on_message")
def run_ai_on_message(
    *,
    thread_id: int,
    user_message_id: int,
    override: dict | None = None,
    parent_message_id: int | None = None,
) -> dict:
    thread = Thread.objects.select_related("profile").get(id=thread_id)
    user_msg = Message.objects.get(id=user_message_id)

    try:
        provider_name, model_id = resolve_provider_and_model(
            thread=thread,
            message=user_msg,
            override=override,
        )
    except ResolutionError as exc:
        _fail(thread_id=thread_id, parent_message_id=parent_message_id, error=str(exc))
        return {"ok": False, "error": "no_provider"}

    try:
        cfg = ProviderConfig.objects.get(provider=provider_name)
    except ProviderConfig.DoesNotExist:
        _fail(
            thread_id=thread_id,
            parent_message_id=parent_message_id,
            error=f"No ProviderConfig row for '{provider_name}'. Visit /settings.",
        )
        return {"ok": False, "error": "no_key"}

    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd)
    except CostCapExceededError as exc:
        _fail(
            thread_id=thread_id,
            parent_message_id=parent_message_id,
            error=str(exc),
            event="cost_capped",
        )
        return {"ok": False, "error": "cost_capped"}

    req = _build_request(thread, user_msg, provider_name=provider_name)
    req.model = model_id

    assistant = Message.objects.create(
        thread=thread,
        role="assistant",
        content={"text": ""},
        status="streaming",
        parent_message_id=parent_message_id,
    )
    _broadcast(
        thread_id,
        {
            "event": "message_started",
            "message_id": assistant.id,
            "parent_message_id": parent_message_id,
            "provider": provider_name,
            "model": model_id,
        },
    )

    provider = get_provider(provider_name, api_key=cfg.api_key, base_url=cfg.base_url or "")
    t0 = time.perf_counter()
    buffer: list[str] = []
    counts: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    err_container: list[str] = []

    tool_events: list[dict] = []

    last_poll = 0.0
    stopped = False

    def _should_stop() -> bool:
        nonlocal last_poll, stopped
        if stopped:
            return True
        now = time.monotonic()
        if now - last_poll < _STOP_POLL_SECONDS:
            return False
        last_poll = now
        if is_stop_requested(assistant.id):
            stopped = True
        return stopped

    drive = _build_stream_runner(
        buffer,
        counts,
        err_container,
        tool_events,
        provider,
        req,
        thread_id,
        assistant.id,
        _should_stop,
    )
    asyncio.run(drive())
    clear_stop(assistant.id)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    err: str | None = err_container[0] if err_container else None

    with transaction.atomic():
        assistant.refresh_from_db()
        if assistant.status == "failed" and assistant.error == "cancelled":
            # Stop endpoint already marked the message; don't overwrite cancellation.
            AIRun.objects.create(
                message=assistant,
                provider=provider_name,
                model=model_id,
                status="failed",
                error="cancelled",
                latency_ms=latency_ms,
                input_tokens=counts["input_tokens"],
                output_tokens=counts["output_tokens"],
            )
            return {"ok": False, "error": "cancelled"}

        assistant.content = {"text": "".join(buffer)}
        if err:
            assistant.status = "failed"
            assistant.error = err
            assistant.save()
            AIRun.objects.create(
                message=assistant,
                provider=provider_name,
                model=model_id,
                status="failed",
                error=err,
                latency_ms=latency_ms,
            )
            _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": err})
            return {"ok": False, "error": err}

        assistant.status = "done"
        assistant.save()
        _persist_tool_calls(assistant, tool_events)

        cost = (
            cost_usd_for(provider_name, model_id, TokenUsage(**counts))
            if any(counts.values())
            else Decimal("0")
        )
        AIRun.objects.create(
            message=assistant,
            provider=provider_name,
            model=model_id,
            cost_usd=cost,
            latency_ms=latency_ms,
            status="done",
            **counts,
        )
        _broadcast(
            thread_id,
            {
                "event": "message_done",
                "message_id": assistant.id,
                "cost_usd": str(cost),
            },
        )
        _broadcast(
            thread_id,
            {
                "event": "cost",
                "message_id": assistant.id,
                "parent_message_id": parent_message_id,
                "cost_usd": str(cost),
                "tokens_in": counts["input_tokens"],
                "tokens_out": counts["output_tokens"],
                "tokens_cached": counts["cached_tokens"],
                "duration_ms": latency_ms,
            },
        )
        return {"ok": True}
