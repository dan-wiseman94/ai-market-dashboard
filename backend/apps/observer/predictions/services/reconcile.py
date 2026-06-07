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
    from apps.observer.models import AIPrediction

    return (
        AIPrediction.objects.filter(ticker=ticker.upper(), status="open")
        .order_by("-predicted_at")
        .first()
    )


def open_divergences(*, include_partial: bool = True) -> list[dict]:
    """Open theses whose direction conflicts with the AI's CURRENT live call on
    the same ticker — a proactive risk surface (M13 F7 dashboard rollup).

    ``diverge`` (opposite calls) is always included; ``partial`` (one side
    neutral) is included unless ``include_partial`` is False. Theses with no
    current AI view are skipped (nothing to reconcile). Highest-conviction first.
    """
    from apps.observer.models import AIPrediction
    from apps.thesis.models import Thesis

    theses = list(Thesis.objects.filter(status="open").order_by("-conviction", "-opened_at"))
    if not theses:
        return []
    # One query for every ticker's current (latest open) AI view — not one per
    # thesis. This runs on every dashboard load, so the N+1 actually mattered.
    tickers = {t.ticker.upper() for t in theses}
    views: dict[str, AIPrediction] = {}
    for p in AIPrediction.objects.filter(ticker__in=tickers, status="open").order_by(
        "ticker", "-predicted_at"
    ):
        views.setdefault(p.ticker, p)  # first row per ticker = latest predicted_at

    out: list[dict] = []
    for t in theses:
        ai = views.get(t.ticker.upper())
        if ai is None:
            continue
        agreement = reconcile_directions(t.direction, ai.direction)
        if agreement == "agree" or (agreement == "partial" and not include_partial):
            continue
        out.append(
            {
                "thesis_id": t.id,
                "ticker": t.ticker,
                "title": t.title,
                "thesis_direction": t.direction,
                "conviction": t.conviction,
                "ai_direction": ai.direction,
                "ai_confidence": round(ai.confidence, 4),
                "ai_horizon_days": ai.horizon_days,
                "agreement": agreement,
            }
        )
    return out


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
