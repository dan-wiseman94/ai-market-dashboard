"""Messages Batch submission + polling for observer schedules.

Flow:
1. submit_watchlist_batch(schedule_id) → one Anthropic batch with N custom_ids,
   where N = len(schedule.default_watchlist_tickers). Returns batch_id.
2. Celery beat polls open batches via poll_batch(); on "ended" status,
   results are pulled and written as assistant Messages on the observer thread.
"""

from __future__ import annotations

import logging

from anthropic import Anthropic

from apps.observer.models import ObserverSchedule
from apps.observer.services.threads import get_or_create_observer_thread
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message

log = logging.getLogger(__name__)


def _anthropic_client(provider: str = "claude") -> Anthropic:
    cfg = ProviderConfig.objects.get(provider=provider)
    return Anthropic(api_key=cfg.api_key, base_url=cfg.base_url or None)


def submit_watchlist_batch(schedule_id: int) -> str:
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)
    tickers = sched.default_watchlist_tickers or []
    if not tickers:
        raise ValueError(f"schedule {schedule_id}: no watchlist tickers to batch")

    provider_name = sched.override_provider or sched.profile.default_provider
    cfg = ProviderConfig.objects.get(provider=provider_name)
    model = sched.override_model or cfg.default_model or "claude-opus-4-8"

    requests = [
        {
            "custom_id": ticker,
            "params": {
                "model": model,
                "max_tokens": 800,
                "system": sched.profile.style or "",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Objective: {sched.objective_template}\n"
                            f"Ticker: {ticker}\n"
                            f"Return a one-paragraph overnight summary."
                        ),
                    }
                ],
            },
        }
        for ticker in tickers
    ]
    client = _anthropic_client(provider_name)
    batch = client.messages.batches.create(requests=requests)  # type: ignore[arg-type]
    sched.last_batch_id = batch.id
    sched.save(update_fields=["last_batch_id"])
    return batch.id


def poll_batch(schedule_id: int, batch_id: str) -> int:
    """If the batch is ended, write results to the thread and return the count."""
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)
    provider_name = sched.override_provider or sched.profile.default_provider
    client = _anthropic_client(provider_name)

    status = client.messages.batches.retrieve(batch_id).processing_status
    if status != "ended":
        log.info("batch %s not ended (%s), skipping", batch_id, status)
        return 0

    thread = get_or_create_observer_thread(sched.profile)
    count = 0
    for result in client.messages.batches.results(batch_id):
        ticker = result.custom_id
        if result.result.type == "succeeded":
            text_parts = [
                block.text
                for block in result.result.message.content
                if getattr(block, "type", None) == "text" and hasattr(block, "text")
            ]
            text = f"[{ticker}] " + " ".join(text_parts)
            Message.objects.create(
                thread=thread,
                role="assistant",
                content={"text": text},
                status="done",
            )
        else:
            err = getattr(result.result, "error", None)
            msg_text = f"[{ticker}] batch failed: {getattr(err, 'message', 'unknown')}"
            Message.objects.create(
                thread=thread,
                role="assistant",
                content={"text": msg_text},
                status="failed",
                error=getattr(err, "message", ""),
            )
        count += 1
    return count
