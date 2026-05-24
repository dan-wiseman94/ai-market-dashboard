"""Replay a trigger DSL against stored OHLC bars for a date range.

Builds a per-bar 'snapshot' shaped like what triggers.metrics emits at runtime,
then runs the existing evaluator. Supports price/pct_change leaves only; other
metrics (vix, position_pl) need a live snapshot and are skipped when replaying.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.market.models import OHLCBar
from apps.triggers.evaluator import evaluate as evaluate_condition
from apps.triggers.evaluator import iter_leaves


@dataclass
class BacktestMatch:
    ts: datetime
    values: dict[str, float | None]


def backtest(
    condition: dict,
    *,
    start: datetime,
    end: datetime,
    timeframe: str = "1d",
) -> list[BacktestMatch]:
    """Replay the condition over daily closes between start and end."""
    tickers = _unique_tickers(condition)
    if not tickers:
        return []

    bars = OHLCBar.objects.filter(
        ticker__in=tickers,
        ts__gte=start,
        ts__lte=end,
        timeframe=timeframe,
    ).order_by("ts")
    by_ts: dict[datetime, dict[str, OHLCBar]] = {}
    for bar in bars:
        by_ts.setdefault(bar.ts, {})[bar.ticker] = bar

    matches: list[BacktestMatch] = []
    prev_closes: dict[str, float] = {}
    for ts in sorted(by_ts):
        per_ticker = by_ts[ts]
        snapshot: dict[str, float | None] = {}
        for ticker, bar in per_ticker.items():
            close = float(bar.close)
            snapshot[f"price:{ticker}"] = close
            prev = prev_closes.get(ticker)
            if prev is not None and prev > 0:
                # pct_change keyed the way evaluator.leaf_key expects: pct_change:<ticker>:<window>
                # Raw decimal to match live metrics.py (0.01 == 1%).
                pct = (close - prev) / prev
                for window in ("1m", "5m", "15m", "1h", "1d"):
                    snapshot[f"pct_change:{ticker}:{window}"] = pct
            prev_closes[ticker] = close

        matched, values = evaluate_condition(condition, snapshot)
        if matched:
            matches.append(BacktestMatch(ts=ts, values=values))
    return matches


def _unique_tickers(condition: dict) -> set[str]:
    return {
        leaf["ticker"]
        for leaf in iter_leaves(condition)
        if isinstance(leaf.get("ticker"), str) and leaf["ticker"]
    }
