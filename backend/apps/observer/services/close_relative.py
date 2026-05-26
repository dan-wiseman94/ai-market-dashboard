"""Beat-driven firing for relative_to_close schedules (half-day-safe)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from apps.market.calendar import calendar_for, session_close_on
from apps.observer.models import ObserverSchedule

log = logging.getLogger(__name__)


def fire_due_close_relative(now: datetime | None = None) -> dict:
    now = now or timezone.now()
    fired = 0
    scheds = ObserverSchedule.objects.filter(enabled=True, fire_mode="relative_to_close")
    for s in scheds:
        symbols = s.default_watchlist_tickers or ["SPY"]
        market = calendar_for(symbols[0])
        close = session_close_on(market, now.date())
        if close is None:
            continue  # not a trading day for this market
        fire_at = close - timedelta(minutes=s.close_offset_minutes)
        if not (fire_at <= now < fire_at + timedelta(minutes=1)):
            continue
        if s.last_fired_at and s.last_fired_at.date() == now.date():
            continue  # once-per-day guard (closes the double-fire race)
        s.last_fired_at = now
        s.save(update_fields=["last_fired_at"])
        from apps.observer.tasks import run_observer_task

        run_observer_task.delay(schedule_id=s.id)
        fired += 1
    return {"fired": fired}
