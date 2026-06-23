"""Consistency sentinel (#15).

Flag a new directional call that contradicts the AI's own stated view — the
per-ticker house view (``CoverageNote.stance``) or a still-open ``AIPrediction``
in the opposite direction. Pure/defensive: never raises.

CoverageNote uses ``bull``/``bear``/``neutral``; AIPrediction uses
``bullish``/``bearish``/``neutral`` — mapped here.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_OPP_DIR = {"bullish": "bearish", "bearish": "bullish"}
_DIR_TO_STANCE = {"bullish": "bull", "bearish": "bear", "neutral": "neutral"}


def find_contradictions(ticker: str, direction: str) -> list[dict]:
    """Conflicting prior views for a ``(ticker, direction)`` call. ``[]`` for a
    neutral call, a blank ticker, or when nothing opposes."""
    if direction not in _OPP_DIR:
        return []
    ticker = (ticker or "").upper()
    if not ticker:
        return []

    out: list[dict] = []
    try:
        from apps.strategy.models import CoverageNote

        note = CoverageNote.objects.filter(ticker=ticker).first()
        if note and note.stance in ("bull", "bear") and _DIR_TO_STANCE[direction] != note.stance:
            out.append({"source": "coverage", "stance": note.stance, "ticker": ticker})
    except Exception:
        log.debug("consistency: lookup failed", exc_info=True)

    try:
        from apps.observer.models import AIPrediction

        opp = _OPP_DIR[direction]
        for p in AIPrediction.objects.filter(ticker=ticker, status="open", direction=opp):
            out.append({"source": "prediction", "direction": opp, "prediction_id": p.id})
    except Exception:
        log.debug("consistency: lookup failed", exc_info=True)
    return out


def open_contradictions() -> list[dict]:
    """Current open predictions whose direction opposes the ticker's house view —
    the 'reconcile these' list. Two queries (CoverageNote + predictions); no N+1."""
    from apps.observer.models import AIPrediction
    from apps.strategy.models import CoverageNote

    stances = dict(CoverageNote.objects.values_list("ticker", "stance"))
    out: list[dict] = []
    for p in (
        AIPrediction.objects.filter(status="open", direction__in=("bullish", "bearish"))
        .order_by("-predicted_at")
        .values("id", "ticker", "direction", "predicted_at")
    ):
        stance = stances.get(p["ticker"])
        if stance in ("bull", "bear") and _DIR_TO_STANCE[p["direction"]] != stance:
            out.append(
                {
                    "ticker": p["ticker"],
                    "prediction_direction": p["direction"],
                    "stance": stance,
                    "prediction_id": p["id"],
                    "predicted_at": p["predicted_at"].isoformat(),
                }
            )
    return out
