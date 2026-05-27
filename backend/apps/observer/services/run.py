"""Orchestrates a single observer fire."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured
from apps.market.calendar import any_market_open
from apps.observer.models import ObserverSchedule
from apps.observer.schemas import ObservationReport
from apps.observer.services.notifications import notify
from apps.observer.services.threads import get_or_create_observer_thread
from apps.secrets.models import ProviderConfig
from apps.snapshots.serializer import serialize_for_ai
from apps.snapshots.services import capture
from apps.threads.models import Message
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def _stamp_fired(sched: ObserverSchedule) -> None:
    sched.last_fired_at = timezone.now()
    sched.save(update_fields=["last_fired_at"])


def run_observer(schedule_id: int) -> int | None:
    """Fire one observer iteration. Returns snapshot_id, or None on skip."""
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)

    if not sched.enabled:
        log.info("observer %s skipped: disabled", schedule_id)
        return None

    if sched.market_hours_only and not any_market_open(sched.default_watchlist_tickers):
        log.info("observer %s skipped: all watched markets closed", schedule_id)
        return None

    thread = get_or_create_observer_thread(sched.profile)
    provider_name = sched.override_provider or sched.profile.default_provider
    model_name = sched.override_model or sched.profile.default_model

    # Resolve caps — Infinity daily / None monthly when no ProviderConfig row exists.
    cfg = ProviderConfig.objects.filter(provider=provider_name).first()
    if cfg is None:
        log.warning(
            "observer %s: no ProviderConfig for %s, skipping cost-cap enforcement",
            schedule_id,
            provider_name,
        )
        cap_usd: Decimal = Decimal("Infinity")
        monthly_cap: Decimal | None = None
    else:
        cap_usd = cfg.daily_cost_cap_usd
        monthly_cap = cfg.monthly_cost_cap_usd

    # Cost-cap check: write placeholder Message instead of running if exceeded.
    try:
        check_daily_cap(provider_name, cap_usd=cap_usd)
        check_monthly_cap(provider_name, cap_usd=monthly_cap)
    except CostCapExceededError as exc:
        Message.objects.create(
            thread=thread,
            role="system",
            content={
                "text": (
                    f"Observer fire skipped at {timezone.now():%Y-%m-%d %H:%M UTC}: "
                    f"cost cap exceeded — {exc}"
                )
            },
            status="done",
        )
        _stamp_fired(sched)
        return None

    snap = capture(
        profile=sched.profile,
        objective=sched.objective_template,
        includes=sched.default_includes or sched.profile.default_includes,
        source="observer",
        watchlist_tickers=sched.default_watchlist_tickers,
    )

    if sched.use_batch:
        from apps.observer.services.batch import submit_watchlist_batch

        try:
            submit_watchlist_batch(sched.id)
        except Exception as exc:
            log.exception("observer %s batch submit failed: %s", sched.id, exc)
        _stamp_fired(sched)
        return snap.id

    if sched.mode == "diff":
        from apps.snapshots.diff import diff_sections
        from apps.snapshots.models import Snapshot

        prev_snap = (
            Snapshot.objects.filter(profile=sched.profile, status="ready")
            .exclude(id=snap.id)
            .order_by("-created_at")
            .first()
        )
        if prev_snap is not None:
            prev_sections = {s.kind: s.payload for s in prev_snap.sections.all()}
            curr_sections = {s.kind: s.payload for s in snap.sections.all()}
            delta_text = diff_sections(prev_sections, curr_sections)
            payload_text = (
                f"Objective: {sched.objective_template}\n\n"
                f"Delta since snapshot #{prev_snap.id}:\n{delta_text}"
            )
        else:
            payload_text = serialize_for_ai(snap, provider=provider_name, model=model_name)
    else:
        payload_text = serialize_for_ai(snap, provider=provider_name, model=model_name)

    msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": payload_text},
        snapshot_ref=snap,
        status="done",
    )

    if sched.structured:
        _run_structured_and_record(sched, thread, payload_text, provider_name, cfg)
    else:
        override: dict = {}
        if sched.override_provider:
            override["provider"] = sched.override_provider
        if sched.override_model:
            override["model"] = sched.override_model
        run_ai_on_message.delay(
            thread_id=thread.id,
            user_message_id=msg.id,
            override=override or None,
        )

    _stamp_fired(sched)

    notify(
        user_id=None,
        kind="observer_done",
        title=f"Observer fired: {sched.name}",
        body=f"Snapshot #{snap.id} captured for {sched.profile.name}",
        link=f"/threads/observer/{sched.profile.id}",
    )
    return snap.id


def _run_structured_and_record(
    sched: ObserverSchedule,
    thread,
    payload_text: str,
    provider_name: str,
    cfg: ProviderConfig | None,
) -> None:
    """Invoke messages.parse with ObservationReport and persist the result."""
    if cfg is None or not cfg.api_key:
        Message.objects.create(
            thread=thread,
            role="system",
            content={"text": f"Observer {sched.name}: no {provider_name} key configured"},
            status="failed",
            error="no_key",
        )
        return
    model_id = sched.override_model or cfg.default_model or "claude-opus-4-7"
    try:
        report = run_structured(
            api_key=cfg.api_key,
            model=model_id,
            system=sched.profile.style or "",
            user=payload_text,
            output_model=ObservationReport,
            base_url=cfg.base_url or "",
        )
    except Exception as exc:
        Message.objects.create(
            thread=thread,
            role="assistant",
            content={"text": f"Structured run failed: {exc}"},
            status="failed",
            error=str(exc),
        )
        return
    Message.objects.create(
        thread=thread,
        role="assistant",
        content={"kind": "structured_observation", "report": report.model_dump()},
        status="done",
    )
