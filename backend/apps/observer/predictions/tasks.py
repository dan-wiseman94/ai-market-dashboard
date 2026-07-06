"""Auto-resolution of due AI predictions.

Deterministic and AI-free: when a prediction's horizon elapses, score it against
the actual forward return (corporate-action-adjusted, via apps.market.returns)
and stamp a verdict. Mirrors thesis.run_due_postmortems, including the idempotent
``open → resolving`` claim so a beat re-tick or a manual resolve-now can't
double-resolve. Look-ahead-safe by construction: resolve_at = predicted_at +
horizon, and we only run at/after resolve_at.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.market.returns import direction_verdict, forward_return_pct, nearest_bar_close
from apps.observer.models import AIPrediction

log = logging.getLogger(__name__)


def resolve_prediction(pred_id: int) -> bool:
    """Resolve one prediction. Returns True if THIS call resolved it, False if it
    was already claimed/resolved (idempotent — safe to overlap)."""
    claimed = AIPrediction.claim(pred_id, frm="open", to="resolving")
    if not claimed:
        return False
    pred = AIPrediction.objects.get(id=pred_id)
    fwd = forward_return_pct(pred.ticker, pred.predicted_at, pred.resolve_at)
    pred.forward_return_pct = fwd
    pred.verdict = direction_verdict(pred.direction, fwd)
    pred.status = "resolved"
    pred.resolved_at = timezone.now()
    pred.save(
        update_fields=["forward_return_pct", "verdict", "status", "resolved_at", "updated_at"]
    )
    return True


@shared_task(name="observer.resolve_due_predictions")
def resolve_due() -> dict:
    """Resolve every open prediction whose horizon has elapsed. Per-row failures
    are logged and skipped — one bad row never blocks the rest."""
    now = timezone.now()
    due = list(
        AIPrediction.objects.filter(status="open", resolve_at__lte=now).values_list("id", flat=True)
    )
    resolved = 0
    for pid in due:
        try:
            if resolve_prediction(pid):
                resolved += 1
        except Exception as exc:  # one bad row must not block the batch
            log.warning("predictions.resolve_due %s failed: %s", pid, exc)
    return {"due": len(due), "resolved": resolved}


def _is_breached(direction: str, price: float, invalidation: float) -> bool:
    """A bullish call is invalidated by trading at/below its support; a bearish
    call at/above its resistance. Neutral calls carry no price (never breach)."""
    if direction == "bullish":
        return price <= invalidation
    if direction == "bearish":
        return price >= invalidation
    return False


@shared_task(name="observer.check_prediction_invalidations")
def check_invalidations() -> dict:
    """Mark open predictions whose invalidation level has been breached BEFORE
    their horizon, and notify. Only predictions carrying an
    ``invalidation_price`` are checked, so this is low-noise by construction.
    Early-warning: 'the AI's own call is being proven wrong before it resolves.'
    """
    now = timezone.now()
    qs = AIPrediction.objects.filter(
        status="open", invalidation_price__isnull=False, resolve_at__gt=now
    )
    invalidated = 0
    for pred in qs:
        try:
            inv = pred.invalidation_price  # qs filters invalidation_price__isnull=False
            price = nearest_bar_close(pred.ticker, now)
            if inv is None or price is None or not _is_breached(pred.direction, price, float(inv)):
                continue
            pred.status = "invalidated"
            pred.invalidated_at = now
            pred.save(update_fields=["status", "invalidated_at", "updated_at"])
            _notify_invalidated(pred, price)
            invalidated += 1
        except Exception as exc:  # one bad row must not block the batch
            log.warning("predictions.check_invalidations %s failed: %s", pred.id, exc)
    return {"invalidated": invalidated}


def _notify_invalidated(pred, price: float) -> None:
    """Best-effort notification — never raises out of the check loop."""
    try:
        from apps.observer.services.notifications import notify

        notify(
            user_id=None,
            kind="pred_invalid",
            title=f"AI {pred.direction} call on {pred.ticker} invalidated",
            body=(
                f"{pred.ticker} traded {price:g}, breaking the AI's invalidation level "
                f"{float(pred.invalidation_price):g} before its {pred.horizon_days}d horizon."
            ),
            link="/scorecard",
        )
    except Exception as exc:
        log.warning("predictions.notify_invalidated %s failed: %s", pred.id, exc)
