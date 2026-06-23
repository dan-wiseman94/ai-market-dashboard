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

from apps.observer.models import AIPrediction

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


def _current_price(snapshot, ticker: str) -> float | None:
    """Primary-ticker last from the snapshot's own quotes section (no fetch).
    Best-effort — any odd shape / missing section yields None."""
    try:
        for sec in snapshot.sections.all():
            if sec.kind == "quotes" and isinstance(sec.payload, dict):
                row = sec.payload.get(ticker)
                if isinstance(row, dict) and row.get("last") is not None:
                    return float(row["last"])
    except Exception:
        return None
    return None


def _invalidation_price_from_levels(report, direction: str, current_price: float | None):
    """Heuristic invalidation level from the report's ``key_levels`` (M13 F5):
    a bullish call is invalidated by breaking the nearest **support below** the
    current price; a bearish call by breaking the nearest **resistance above**.
    Neutral calls get no price. ``None`` when no qualifying level exists. When the
    current price is unknown the nearest-by-price filter is relaxed.
    """
    levels = getattr(report, "key_levels", []) or []
    if direction == "bullish":
        below = [
            lvl.price
            for lvl in levels
            if getattr(lvl, "kind", "") == "support"
            and (current_price is None or lvl.price < current_price)
        ]
        return max(below) if below else None
    if direction == "bearish":
        above = [
            lvl.price
            for lvl in levels
            if getattr(lvl, "kind", "") == "resistance"
            and (current_price is None or lvl.price > current_price)
        ]
        return min(above) if above else None
    return None


def _expected_move_pct(snapshot, horizon_days: int) -> float | None:
    """1σ options-implied move frozen at decision time, from the snapshot's own
    chain section (look-ahead-safe — the chain as captured). Best-effort: a missing
    chain / odd shape / any error yields None and never breaks extraction."""
    try:
        from apps.market.services.expected_move import for_horizon

        for sec in snapshot.sections.all():
            if sec.kind == "chain" and isinstance(sec.payload, dict):
                return for_horizon(sec.payload, horizon_days)
    except Exception:
        return None
    return None


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
    inv_price = _invalidation_price_from_levels(report, direction, _current_price(snapshot, ticker))

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

    pred = AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=horizon,
        confidence=confidence,
        expected_move_pct=_expected_move_pct(snapshot, horizon),
        rationale=(getattr(report, "headline", "") or "")[:500],
        invalidation_note=_invalidation_for(report, ticker),
        invalidation_price=inv_price,
        provider=provider,
        model=model,
        source_message=message,
        source_snapshot=snapshot,
        profile=profile,
        predicted_at=predicted_at,
        resolve_at=_resolve_at(ticker, predicted_at, horizon),
    )
    _flag_contradictions(ticker, direction)
    return pred


def _flag_contradictions(ticker: str, direction: str) -> None:
    """#15: notify when this new call contradicts the house view / an open call.
    Best-effort — a sentinel failure must never break extraction."""
    try:
        from apps.observer.predictions.services.consistency import find_contradictions
        from apps.observer.services.notifications import notify

        conflicts = find_contradictions(ticker, direction)
        if not conflicts:
            return
        srcs = ", ".join(
            f"{c['stance']} house view"
            if c["source"] == "coverage"
            else f"open {c['direction']} call"
            for c in conflicts
        )
        notify(
            user_id=None,
            kind="contra",
            title=f"Inconsistent view: {ticker}",
            body=f"New {direction} {ticker} call contradicts {srcs}.",
            link="/scorecard",
        )
    except Exception:
        log.debug("consistency sentinel failed for %s", ticker, exc_info=True)
