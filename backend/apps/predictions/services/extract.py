"""Promote a structured observation's directional call into an AIPrediction (M13 F1).

Zero added AI cost — this reads the ``ObservationReport`` the observer already
produced. Best-effort and side-effect-isolated: the observer wraps the call so a
failure here never breaks a fire.

Dedup rule: at most one ``open`` prediction per ``(ticker, horizon_days, profile)``.
A same-direction re-fire is a **no-op** (the open call stands, frozen as-stated so
calibration scores the call as it was made). A direction **flip** resolves the
prior open call early as ``invalidated`` ("the AI changed its mind") and creates a
fresh one.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.predictions.models import AIPrediction

log = logging.getLogger(__name__)

DEFAULT_HORIZON_DAYS = 7


def _confidence_for(report, ticker: str) -> float | None:
    """Stated ``predicted_confidence``, else the mean of the per-signal confidences
    (the schema's own documented fallback), preferring signals on ``ticker``."""
    stated = getattr(report, "predicted_confidence", None)
    if stated is not None:
        return float(stated)
    signals = list(getattr(report, "signals", []) or [])
    scoped = [s for s in signals if getattr(s, "ticker", "").upper() == ticker] or signals
    vals = [float(s.confidence) for s in scoped if getattr(s, "confidence", None) is not None]
    return sum(vals) / len(vals) if vals else None


def _invalidation_for(report, ticker: str) -> str:
    for s in getattr(report, "signals", []) or []:
        if getattr(s, "ticker", "").upper() == ticker and getattr(s, "invalidation", ""):
            return str(s.invalidation)[:300]
    return ""


def _resolve_at(ticker: str, predicted_at, horizon_days: int):
    """predicted_at + horizon trading sessions on the ticker's calendar."""
    from apps.market.calendar import add_trading_days, calendar_for

    return add_trading_days(calendar_for(ticker), predicted_at, horizon_days)


def extract_from_observation(
    report,
    *,
    snapshot=None,
    message=None,
    provider: str,
    model: str,
    profile=None,
) -> AIPrediction | None:
    """Create/update an ``AIPrediction`` from a structured ``ObservationReport``.

    Returns the prediction, or ``None`` when the report carries no usable
    directional call (no ``predicted_direction``, no resolvable ticker, or no
    derivable confidence — calibration needs all three).
    """
    direction = getattr(report, "predicted_direction", None)
    if direction not in ("bullish", "bearish", "neutral"):
        return None

    ticker = (getattr(snapshot, "primary_ticker", "") or "").upper()
    if not ticker:
        signals = list(getattr(report, "signals", []) or [])
        ticker = signals[0].ticker.upper() if signals else ""
    if not ticker:
        return None

    confidence = _confidence_for(report, ticker)
    if confidence is None:
        return None

    horizon = int(getattr(report, "predicted_horizon_days", None) or DEFAULT_HORIZON_DAYS)
    predicted_at = getattr(message, "created_at", None) or timezone.now()

    existing = AIPrediction.objects.filter(
        ticker=ticker, horizon_days=horizon, profile=profile, status="open"
    ).first()
    if existing is not None:
        if existing.direction == direction:
            return existing  # the open call stands; frozen as-stated
        # Direction flipped: retire the old call early, then create a fresh one.
        existing.status = "invalidated"
        existing.invalidated_at = timezone.now()
        existing.save(update_fields=["status", "invalidated_at", "updated_at"])

    return AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=horizon,
        confidence=confidence,
        rationale=(getattr(report, "headline", "") or "")[:500],
        invalidation_note=_invalidation_for(report, ticker),
        provider=provider,
        model=model,
        source_message=message,
        source_snapshot=snapshot,
        profile=profile,
        predicted_at=predicted_at,
        resolve_at=_resolve_at(ticker, predicted_at, horizon),
    )
