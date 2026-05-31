"""Thesis ↔ AI-prediction reconciliation (M13 F7).

A read-side join over existing data: where the trader holds a Thesis on a ticker
and the AI has a live call on the same ticker, surface whether they agree. Gives
a second opinion at decision time — the two forecasting loops compared head to head.
"""

from __future__ import annotations


def reconcile_directions(thesis_dir: str, ai_dir: str) -> str:
    """``agree`` (same call), ``diverge`` (bullish vs bearish), or ``partial``
    (one side neutral, the other directional)."""
    if thesis_dir == ai_dir:
        return "agree"
    if "neutral" in (thesis_dir, ai_dir):
        return "partial"
    return "diverge"


def current_ai_view(ticker: str):
    """The AI's current live call on ``ticker`` — the most recent ``open``
    prediction — or ``None``. Resolved/invalidated calls are not "current"."""
    from apps.predictions.models import AIPrediction

    return (
        AIPrediction.objects.filter(ticker=ticker.upper(), status="open")
        .order_by("-predicted_at")
        .first()
    )


def ai_view_payload(ticker: str, against: str | None = None) -> dict:
    """JSON-ready current AI view for ``ticker``. ``against`` (a thesis direction)
    adds an ``agreement`` verdict; omitted ⇒ ``agreement`` is null."""
    ticker = (ticker or "").upper()
    pred = current_ai_view(ticker) if ticker else None
    if pred is None:
        return {"ticker": ticker, "has_view": False}
    return {
        "ticker": ticker,
        "has_view": True,
        "direction": pred.direction,
        "confidence": round(pred.confidence, 4),
        "horizon_days": pred.horizon_days,
        "predicted_at": pred.predicted_at.isoformat(),
        "rationale": pred.rationale,
        "provider": pred.provider,
        "model": pred.model,
        "agreement": reconcile_directions(against, pred.direction) if against else None,
    }
