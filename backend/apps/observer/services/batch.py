"""Messages Batch submission + polling for observer schedules.

Flow:
1. submit_watchlist_batch(schedule_id, snapshot_id=None) → one Anthropic batch
   with N custom_ids, where N = len(schedule.default_watchlist_tickers). Each
   request is grounded in the ticker's market data from the captured snapshot.
   Returns batch_id.
2. Celery beat polls open batches via poll_batch(); on "ended" status, results
   are pulled and written as assistant Messages on the observer thread, and
   each result's usage is recorded as an AIRun (at the 50%-discounted batch
   rate) so batch spend counts against the caps and /api/costs.
"""

from __future__ import annotations

import json
import logging

from anthropic import Anthropic
from cryptography.fernet import InvalidToken

from apps.ai.catalog import CLAUDE_FAMILY_PROVIDERS, DEFAULT_CLAUDE_MODEL
from apps.ai.cost import BATCH_COST_MULTIPLIER, record_ai_run
from apps.ai.providers import client_kwargs
from apps.ai.providers.claude_structured import token_usage_from_anthropic
from apps.ai.types import TokenUsage
from apps.observer.models import ObserverSchedule
from apps.observer.services.threads import get_or_create_observer_thread
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message

log = logging.getLogger(__name__)


def _require_claude(provider_name: str, schedule_id: int) -> None:
    """Messages Batches is an Anthropic API — refuse to wrap a non-Claude
    ProviderConfig in an Anthropic client (its key would be sent to
    api.anthropic.com and every request would fail with an opaque 401)."""
    if provider_name not in CLAUDE_FAMILY_PROVIDERS:
        raise ValueError(
            f"schedule {schedule_id}: batch mode requires a Claude provider, got {provider_name!r}"
        )


def _anthropic_client(provider: str = "claude") -> Anthropic:
    try:
        cfg = ProviderConfig.objects.get(provider=provider)
    except InvalidToken as exc:
        # Undecryptable key (key/salt rotation) — fail the batch with a clear message
        # instead of an opaque InvalidToken bubbling out of the Celery task.
        raise ValueError(
            f"{provider} API key could not be decrypted (encryption key changed); "
            "re-enter it in Settings → Providers."
        ) from exc
    return Anthropic(api_key=cfg.api_key, base_url=cfg.base_url or None, **client_kwargs())


def _market_context(snapshot_id: int | None, tickers: list[str]) -> dict[str, str]:
    """Per-ticker market-data lines from the captured snapshot, keyed by ticker.

    Grounds each batch request in the data the fire just captured instead of
    letting the model answer from training data alone. Missing snapshot or
    sections in any non-"done" state degrade to fewer (or no) lines — never
    raise, a submit must not fail because a section did.
    """
    if snapshot_id is None:
        return {}
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(id=snapshot_id).first()
    if snap is None:
        return {}
    quotes: dict = {}
    ohlc: dict = {}
    q_section = snap.sections.filter(kind="quotes", status="done").first()
    if q_section is not None:
        quotes = (q_section.payload or {}).get("data") or {}
    o_section = snap.sections.filter(kind="ohlc", status="done").first()
    if o_section is not None:
        ohlc = (o_section.payload or {}).get("data") or {}

    out: dict[str, str] = {}
    for ticker in tickers:
        lines: list[str] = []
        quote = quotes.get(ticker)
        if quote:
            lines.append(f"Quote: {json.dumps(quote, default=str)}")
        if ohlc.get("ticker") == ticker and ohlc.get("bars"):
            recent = ohlc["bars"][-10:]
            lines.append(
                f"Recent OHLC bars ({ohlc.get('timeframe', '?')}): "
                f"{json.dumps(recent, default=str)}"
            )
        if lines:
            out[ticker] = "Market data from the captured snapshot:\n" + "\n".join(lines) + "\n"
    return out


def submit_watchlist_batch(schedule_id: int, snapshot_id: int | None = None) -> str:
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)
    tickers = sched.default_watchlist_tickers or []
    if not tickers:
        raise ValueError(f"schedule {schedule_id}: no watchlist tickers to batch")

    provider_name = sched.override_provider or sched.profile.default_provider
    _require_claude(provider_name, sched.id)
    # defer the key here (only default_model is read); _anthropic_client below builds the
    # client and is where an undecryptable key is reported.
    cfg = ProviderConfig.objects.defer("_api_key").get(provider=provider_name)
    model = sched.override_model or cfg.default_model or DEFAULT_CLAUDE_MODEL

    context_by_ticker = _market_context(snapshot_id, tickers)
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
                            f"{context_by_ticker.get(ticker, '')}"
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
    _require_claude(provider_name, sched.id)
    client = _anthropic_client(provider_name)

    status = client.messages.batches.retrieve(batch_id).processing_status
    if status != "ended":
        log.info("batch %s not ended (%s), skipping", batch_id, status)
        return 0

    cfg = ProviderConfig.objects.defer("_api_key").get(provider=provider_name)
    fallback_model = sched.override_model or cfg.default_model or DEFAULT_CLAUDE_MODEL

    thread = get_or_create_observer_thread(sched.profile)
    count = 0
    for result in client.messages.batches.results(batch_id):
        ticker = result.custom_id
        if result.result.type == "succeeded":
            api_message = result.result.message
            text_parts = [
                block.text
                for block in api_message.content
                if getattr(block, "type", None) == "text" and hasattr(block, "text")
            ]
            text = f"[{ticker}] " + " ".join(text_parts)
            msg = Message.objects.create(
                thread=thread,
                role="assistant",
                content={"text": text},
                status="done",
            )
            _record_batch_run(
                provider_name,
                model=getattr(api_message, "model", "") or fallback_model,
                usage=token_usage_from_anthropic(getattr(api_message, "usage", None)),
                message=msg,
            )
        else:
            err = getattr(result.result, "error", None)
            err_text = getattr(err, "message", "") or "unknown"
            msg = Message.objects.create(
                thread=thread,
                role="assistant",
                content={"text": f"[{ticker}] batch failed: {err_text}"},
                status="failed",
                error=getattr(err, "message", ""),
            )
            # Errored results are not billed by Anthropic; the zero-usage AIRun
            # still lands so failures stay visible in the cost ledger.
            _record_batch_run(
                provider_name,
                model=fallback_model,
                usage=TokenUsage(),
                message=msg,
                status="failed",
                error=err_text,
            )
        count += 1
    return count


def _record_batch_run(
    provider_name: str,
    *,
    model: str,
    usage: TokenUsage,
    message: Message,
    status: str = "done",
    error: str = "",
) -> None:
    """Ledger write for one batch result, at the discounted batch rate, so batch
    spend counts against check_daily_cap / check_monthly_cap and /api/costs.
    Best-effort (mirrors run_structured's recorder): a ledger failure must not
    lose the already-written observation Message.
    """
    try:
        record_ai_run(
            provider=provider_name,
            model=model,
            usage=usage,
            message=message,
            status=status,
            error=error,
            cost_multiplier=BATCH_COST_MULTIPLIER,
        )
    except Exception:  # the observation Message is already persisted
        log.warning("poll_batch: failed to record AIRun for message %s", message.id, exc_info=True)
