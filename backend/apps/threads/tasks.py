"""AI run Celery task — drives ClaudeProvider and broadcasts to the thread channel."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import transaction

from apps.ai.cost import CostCapExceededError, check_daily_cap, cost_usd_for
from apps.ai.providers.claude import ClaudeProvider
from apps.ai.types import (
    ChatMessage, DoneEvent, ErrorEvent, RunRequest, TextDelta, UsageEvent,
)
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread


async def _broadcast_async(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(
        f"thread.{thread_id}", {"type": "thread_event", "payload": payload}
    )


def _broadcast(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"thread.{thread_id}", {"type": "thread_event", "payload": payload}
    )


@shared_task(name="threads.run_ai_on_message")
def run_ai_on_message(*, thread_id: int, user_message_id: int) -> dict:
    thread = Thread.objects.select_related("profile").get(id=thread_id)
    profile = thread.profile
    user_msg = Message.objects.get(id=user_message_id)

    provider_name = (profile.default_provider if profile else "claude")
    model_id = (profile.default_model if profile else "claude-sonnet-4-6")

    try:
        cfg = ProviderConfig.objects.get(provider=provider_name)
    except ProviderConfig.DoesNotExist:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=f"No API key configured for provider '{provider_name}'. Visit /settings.",
        )
        _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": assistant.error})
        return {"ok": False, "error": "no_key"}

    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
    except CostCapExceededError as exc:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=str(exc),
        )
        _broadcast(thread_id, {"event": "cost_capped", "message_id": assistant.id, "error": str(exc)})
        return {"ok": False, "error": "cost_capped"}

    system = (profile.style if profile else "")
    history = list(Message.objects.filter(thread=thread, role__in=["user", "assistant"]).order_by("created_at"))
    chat_messages = []
    for m in history:
        chat_messages.append(ChatMessage(role=m.role, content=_extract_text(m)))

    if not any(m.id == user_msg.id for m in history):
        chat_messages.append(ChatMessage(role="user", content=_extract_text(user_msg)))

    req = RunRequest(model=model_id, system=system, messages=chat_messages, cache_system=True)

    assistant = Message.objects.create(
        thread=thread, role="assistant", content={"text": ""}, status="streaming",
    )
    _broadcast(thread_id, {"event": "message_started", "message_id": assistant.id})

    provider = ClaudeProvider(api_key=cfg.api_key, base_url=cfg.base_url or "")
    t0 = time.perf_counter()
    buffer: list[str] = []
    usage = None
    err: str | None = None

    async def drive():
        nonlocal usage, err
        async for evt in provider.run(req):
            if isinstance(evt, TextDelta):
                buffer.append(evt.text)
                await _broadcast_async(thread_id, {
                    "event": "text_delta", "message_id": assistant.id, "text": evt.text,
                })
            elif isinstance(evt, UsageEvent):
                usage = evt.usage
            elif isinstance(evt, ErrorEvent):
                err = evt.message
            elif isinstance(evt, DoneEvent):
                return

    asyncio.run(drive())
    latency_ms = int((time.perf_counter() - t0) * 1000)

    with transaction.atomic():
        if err:
            assistant.content = {"text": "".join(buffer)}
            assistant.status = "failed"
            assistant.error = err
            assistant.save()
            AIRun.objects.create(
                message=assistant, provider=provider_name, model=model_id,
                status="failed", error=err, latency_ms=latency_ms,
            )
            _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": err})
            return {"ok": False, "error": err}

        assistant.content = {"text": "".join(buffer)}
        assistant.status = "done"
        assistant.save()

        cost = Decimal("0")
        if usage is not None:
            cost = cost_usd_for(provider_name, model_id, usage)
        AIRun.objects.create(
            message=assistant, provider=provider_name, model=model_id,
            input_tokens=(usage.input_tokens if usage else 0),
            output_tokens=(usage.output_tokens if usage else 0),
            cached_tokens=(usage.cached_tokens if usage else 0),
            cost_usd=cost, latency_ms=latency_ms, status="done",
        )
        _broadcast(thread_id, {
            "event": "message_done", "message_id": assistant.id, "cost_usd": str(cost),
        })
        return {"ok": True}


def _extract_text(m: Message) -> str:
    c = m.content or {}
    if isinstance(c, dict) and "text" in c:
        return c["text"]
    return str(c)
