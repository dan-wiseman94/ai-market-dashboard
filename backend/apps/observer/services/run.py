"""Orchestrates a single observer fire."""
from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from apps.ai.cost import CostCapExceededError, check_daily_cap
from apps.observer.models import ObserverSchedule
from apps.observer.services.market_hours import is_market_open
from apps.observer.services.notifications import notify
from apps.observer.services.threads import get_or_create_observer_thread
from apps.secrets.models import ProviderConfig
from apps.snapshots.serializer import serialize_for_ai
from apps.snapshots.services import capture
from apps.threads.models import Message
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def run_observer(schedule_id: int) -> int | None:
    """Fire one observer iteration. Returns snapshot_id, or None on skip."""
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)

    if not sched.enabled:
        log.info("observer %s skipped: disabled", schedule_id)
        return None

    if sched.market_hours_only and not is_market_open():
        log.info("observer %s skipped: market closed", schedule_id)
        return None

    thread = get_or_create_observer_thread(sched.profile)
    provider_name = sched.override_provider or sched.profile.default_provider

    # Resolve daily cap — use Infinity when no ProviderConfig row exists (no enforcement).
    try:
        cap_usd: Decimal = ProviderConfig.objects.get(provider=provider_name).daily_cost_cap_usd
    except ProviderConfig.DoesNotExist:
        log.warning(
            "observer %s: no ProviderConfig for %s, skipping cost-cap enforcement",
            schedule_id, provider_name,
        )
        cap_usd = Decimal("Infinity")

    # Cost-cap check: write placeholder Message instead of running if exceeded.
    try:
        check_daily_cap(provider_name, cap_usd=cap_usd)
    except CostCapExceededError:
        Message.objects.create(
            thread=thread, role="system",
            content={"text": (
                f"Observer fire skipped at {timezone.now():%Y-%m-%d %H:%M UTC}: "
                f"daily cost cap reached for {provider_name}."
            )},
            status="done",
        )
        sched.last_fired_at = timezone.now()
        sched.save(update_fields=["last_fired_at"])
        return None

    snap = capture(
        profile=sched.profile,
        objective=sched.objective_template,
        includes=sched.default_includes or sched.profile.default_includes,
        source="observer",
        watchlist_tickers=sched.default_watchlist_tickers,
    )

    msg = Message.objects.create(
        thread=thread, role="user",
        content={"text": serialize_for_ai(snap, provider=provider_name)},
        snapshot_ref=snap, status="done",
    )

    override: dict = {}
    if sched.override_provider:
        override["provider"] = sched.override_provider
    if sched.override_model:
        override["model"] = sched.override_model
    run_ai_on_message.delay(
        thread_id=thread.id, user_message_id=msg.id,
        override=override or None,
    )

    sched.last_fired_at = timezone.now()
    sched.save(update_fields=["last_fired_at"])

    notify(
        user_id=None, kind="observer_done",
        title=f"Observer fired: {sched.name}",
        body=f"Snapshot #{snap.id} captured for {sched.profile.name}",
        link=f"/threads/observer/{sched.profile.id}",
    )
    return snap.id
