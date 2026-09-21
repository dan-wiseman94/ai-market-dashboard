"""Dashboard aggregator — GET /api/dashboard/.

Assembles a command-centre payload from existing data.  Each section is wrapped
with _safe() so a failing section degrades to its default and never 500s the
whole endpoint (mirrors briefing's _safe_section pattern).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import sentry_sdk
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observer.briefing.services.assemble import _theses_section

log = logging.getLogger(__name__)


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:
        log.warning("dashboard.section_failed: %s", exc)
        sentry_sdk.capture_exception(exc)  # no-op unless SENTRY_DSN is configured
        return default


def _events_section() -> dict:
    from apps.market.services.events import upcoming_events
    from apps.profiles.models import WatchlistSymbol

    tickers = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    return upcoming_events(tickers, within_days=7)


def _observer_summary() -> dict:
    from apps.observer.models import ObserverSchedule
    from apps.threads.models import Message, Thread

    enabled_count = ObserverSchedule.objects.filter(enabled=True).count()

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    observer_thread_ids = Thread.objects.filter(kind="observer").values_list("id", flat=True)
    runs_today = Message.objects.filter(
        thread_id__in=observer_thread_ids,
        role="assistant",
        status="done",
        created_at__gte=today_start,
    ).count()

    return {
        "enabled_schedules": enabled_count,
        "runs_today": runs_today,
    }


def _triggers_summary() -> dict:
    from apps.observer.models import EventTrigger, TriggerFiring

    armed_count = EventTrigger.objects.filter(enabled=True).count()

    firings_out = []
    for f in TriggerFiring.objects.select_related("trigger").order_by("-fired_at")[:10]:
        firings_out.append(
            {
                "id": f.id,
                "trigger_id": f.trigger_id,
                "trigger_name": getattr(f.trigger, "name", None),
                "fired_at": f.fired_at.isoformat(),
                "cost_capped": f.cost_capped,
            }
        )

    return {
        "armed_count": armed_count,
        "latest_firings": firings_out,
    }


def _book_section() -> dict:
    from apps.book.services.compute import current_book

    snap = current_book()
    if snap is None:
        return {"hhi": None, "alignment": None, "as_of": None}
    return {
        "hhi": (snap.concentration or {}).get("hhi"),
        "alignment": (snap.regime_fit or {}).get("alignment"),
        "as_of": snap.as_of_date.isoformat() if snap.as_of_date else None,
    }


def _desk_section() -> dict:
    from apps.strategy.models import DeskEntry

    new = DeskEntry.objects.filter(status="new").order_by("-created_at")
    latest = new.first()
    return {"unread": new.count(), "latest": latest.finding if latest else None}


def _regime_section() -> dict:
    from apps.strategy.regime.services.compute import current_regime

    reading = current_regime()
    if reading is None:
        return {"composite": None, "drivers": [], "as_of": None}
    return {
        "composite": reading.composite,
        "drivers": reading.drivers or [],
        "as_of": reading.created_at.isoformat(),
    }


# Full contract-valid shape for the predictions tile — the _safe() default and the
# live payload must stay the same keys (a partial default crashes the SPA tile).
_PREDICTIONS_DEFAULT = {
    "open_count": 0,
    "resolved_30d": 0,
    "invalidated_30d": 0,
    "hit_rate_30d": None,
}


def _predictions_section() -> dict:
    """Prediction Ledger rollup: live calls now, plus how the last 30 days scored.
    ``hit_rate_30d`` counts decisive verdicts only (correct vs incorrect), and is
    None below one decisive call rather than a fabricated 0.0."""
    from apps.observer.models import AIPrediction

    since = timezone.now() - timedelta(days=30)
    agg = AIPrediction.objects.aggregate(
        open_count=Count("id", filter=Q(status="open")),
        resolved_30d=Count("id", filter=Q(status="resolved", resolved_at__gte=since)),
        invalidated_30d=Count("id", filter=Q(status="invalidated", invalidated_at__gte=since)),
        correct=Count("id", filter=Q(verdict="correct", resolved_at__gte=since)),
        incorrect=Count("id", filter=Q(verdict="incorrect", resolved_at__gte=since)),
    )
    decisive = agg["correct"] + agg["incorrect"]
    return {
        "open_count": agg["open_count"],
        "resolved_30d": agg["resolved_30d"],
        "invalidated_30d": agg["invalidated_30d"],
        "hit_rate_30d": round(agg["correct"] / decisive, 4) if decisive else None,
    }


def _latest_briefing_summary() -> dict | None:
    from apps.observer.models import BriefingRun

    run = BriefingRun.objects.order_by("-created_at").first()
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
        "scheduled_date": run.scheduled_date.isoformat() if run.scheduled_date else None,
    }


class DashboardView(APIView):
    def get(self, request: Request) -> Response:
        return Response(
            {
                "theses": _safe(_theses_section, []),
                "events": _safe(_events_section, {"earnings": [], "macro": []}),
                # Defaults must match the frontend contract (DashboardObserver /
                # DashboardTriggers) so a degraded section renders empty instead of
                # crashing the SPA (e.g. triggers.latest_firings.length on undefined).
                "observer": _safe(_observer_summary, {"enabled_schedules": 0, "runs_today": 0}),
                "triggers": _safe(_triggers_summary, {"armed_count": 0, "latest_firings": []}),
                "briefing": _safe(_latest_briefing_summary, None),
                "regime": _safe(_regime_section, {"composite": None, "drivers": [], "as_of": None}),
                "book": _safe(_book_section, {"hhi": None, "alignment": None, "as_of": None}),
                "desk": _safe(_desk_section, {"unread": 0, "latest": None}),
                "predictions": _safe(_predictions_section, dict(_PREDICTIONS_DEFAULT)),
            }
        )
