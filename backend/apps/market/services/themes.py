"""Narrative health for a Theme (#18): participation, leadership, relative strength.

Deterministic, from stored OHLCBar via the split-corrected forward-return helper.
Honest coverage — members with no price history are excluded and metrics are null
below two priced members.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

SPX_SYMBOL = "$SPX"


def theme_health(theme, *, window_days: int = 20, now: datetime | None = None) -> dict:
    from apps.market.returns import forward_return_pct

    now = now or timezone.now()
    start = now - timedelta(days=window_days)

    members: list[dict] = []
    priced: list[tuple[str, float]] = []
    for t in theme.tickers:
        r = forward_return_pct(t, start, now)
        members.append({"ticker": t, "return_pct": round(r, 2) if r is not None else None})
        if r is not None:
            priced.append((t, r))

    spx = forward_return_pct(SPX_SYMBOL, start, now)
    spx_pct = round(spx, 2) if spx is not None else None
    coverage = {"priced": len(priced), "total": len(theme.tickers)}

    if len(priced) < 2:
        return {
            "window_days": window_days,
            "coverage": coverage,
            "breadth": None,
            "mean_return_pct": None,
            "spx_return_pct": spx_pct,
            "relative_strength": None,
            "leadership": None,
            "members": members,
        }

    mean = sum(r for _, r in priced) / len(priced)
    breadth = sum(1 for _, r in priced if r > 0) / len(priced)
    leader = max(priced, key=lambda x: x[1])
    laggard = min(priced, key=lambda x: x[1])
    for m in members:
        if m["return_pct"] is not None:
            m["above_theme"] = m["return_pct"] > mean

    return {
        "window_days": window_days,
        "coverage": coverage,
        "breadth": round(breadth, 4),
        "mean_return_pct": round(mean, 2),
        "spx_return_pct": spx_pct,
        # theme's edge over the tape — positive means the narrative is outperforming
        "relative_strength": round(mean - spx, 2) if spx is not None else None,
        "leadership": {
            "leader": {"ticker": leader[0], "return_pct": round(leader[1], 2)},
            "laggard": {"ticker": laggard[0], "return_pct": round(laggard[1], 2)},
        },
        "members": members,
    }
