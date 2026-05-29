"""Replay a trigger DSL against stored OHLC bars for a date range.

Builds a per-bar 'snapshot' shaped like what triggers.metrics emits at runtime,
then runs the existing evaluator. Supports price, pct_change, and indicator
leaves; live-only metrics (vix, position_pl) are skipped when replaying.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.market.models import OHLCBar
from apps.triggers import indicators as ind
from apps.triggers.dsl import PARAMS_SPEC
from apps.triggers.evaluator import evaluate as evaluate_condition
from apps.triggers.evaluator import iter_leaves, leaf_key

ind_supported = {
    "rsi",
    "sma_spread_pct",
    "atr_pct",
    "dist_from_sma_pct",
    "dist_from_52w_high",
    "dist_from_52w_low",
    "gap_pct",
}


@dataclass
class BacktestMatch:
    ts: datetime
    values: dict[str, float | None]


def _resolved_params(leaf: dict) -> dict:
    """Return params dict with defaults filled in from PARAMS_SPEC."""
    spec = PARAMS_SPEC.get(leaf["metric"], {})
    p = dict(leaf.get("params") or {})
    for k, (_t, default, *_r) in spec.items():
        p.setdefault(k, default)
    return p


def _bar_indicator(
    leaf: dict,
    closes: list[float],
    bars: list[dict],
    last: float,
    today_open: float,
    prev_close: float | None,
) -> float | None:
    """Compute the indicator value for a single bar given its rolling history."""
    m = leaf["metric"]
    p = _resolved_params(leaf)
    if m == "rsi":
        return ind.rsi(closes, p["period"])
    if m == "atr_pct":
        return ind.atr_pct(bars, period=p["period"], last=last)
    if m == "sma_spread_pct":
        return ind.sma_spread_pct(closes, fast=p["fast"], slow=p["slow"])
    if m == "dist_from_sma_pct":
        return ind.dist_from_sma_pct(closes, period=p["period"], last=last)
    if m == "dist_from_52w_high":
        return ind.dist_from_high([b["high"] for b in bars], last=last)
    if m == "dist_from_52w_low":
        return ind.dist_from_low([b["low"] for b in bars], last=last)
    if m == "gap_pct":
        return ind.gap_pct(today_open=today_open, prev_close=prev_close) if prev_close else None
    return None


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

    leaves = iter_leaves(condition)
    closes_hist: dict[str, list[float]] = {}
    bars_hist: dict[str, list[dict]] = {}
    prev_values: dict[str, float | None] = {}
    matches: list[BacktestMatch] = []
    prev_closes: dict[str, float] = {}

    for ts in sorted(by_ts):
        per_ticker = by_ts[ts]
        snapshot: dict[str, float | None] = {}

        for ticker, bar in per_ticker.items():
            close = float(bar.close)
            high, low, op_price = float(bar.high), float(bar.low), float(bar.open)
            snapshot[f"price:{ticker}"] = close
            closes_hist.setdefault(ticker, []).append(close)
            bars_hist.setdefault(ticker, []).append({"high": high, "low": low, "close": close})
            prev = prev_closes.get(ticker)
            if prev is not None and prev > 0:
                pct = (close - prev) / prev
                for window in ("1m", "5m", "15m", "1h", "1d"):
                    snapshot[f"pct_change:{ticker}:{window}"] = pct
            # indicator leaves for this ticker
            for leaf in leaves:
                if leaf.get("ticker") != ticker or leaf["metric"] not in ind_supported:
                    continue
                resolved = _resolved_params(leaf)
                key = leaf_key({**leaf, "params": resolved})
                snapshot[key] = _bar_indicator(
                    leaf,
                    closes_hist[ticker],
                    bars_hist[ticker],
                    close,
                    op_price,
                    prev,
                )
            prev_closes[ticker] = close

        # crossing support: populate _prior: keys from the previous bar's values
        for k, _v in list(snapshot.items()):
            snapshot[f"_prior:{k}"] = prev_values.get(k)

        matched, values = evaluate_condition(condition, snapshot)
        if matched:
            matches.append(BacktestMatch(ts=ts, values=values))

        # update prev_values with non-prior entries for next iteration
        prev_values.update({k: v for k, v in snapshot.items() if not k.startswith("_prior:")})

    return matches


def _unique_tickers(condition: dict) -> set[str]:
    return {
        leaf["ticker"]
        for leaf in iter_leaves(condition)
        if isinstance(leaf.get("ticker"), str) and leaf["ticker"]
    }
