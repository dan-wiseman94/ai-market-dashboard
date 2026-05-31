"""Auto-resolution of due AI predictions (M13 F2).

Deterministic and AI-free: when a prediction's horizon elapses, score it against
the actual forward return (C3 corporate-action-correct, via apps.market.returns)
and stamp a verdict. Mirrors thesis.run_due_postmortems, including the idempotent
``open → resolving`` claim so a beat re-tick or a manual resolve-now can't
double-resolve. Look-ahead-safe by construction: resolve_at = predicted_at +
horizon, and we only run at/after resolve_at.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.market.returns import direction_verdict, forward_return_pct
from apps.predictions.models import AIPrediction

log = logging.getLogger(__name__)


def resolve_prediction(pred_id: int) -> bool:
    """Resolve one prediction. Returns True if THIS call resolved it, False if it
    was already claimed/resolved (idempotent — safe to overlap)."""
    claimed = AIPrediction.objects.filter(id=pred_id, status="open").update(status="resolving")
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


@shared_task(name="predictions.resolve_due")
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
