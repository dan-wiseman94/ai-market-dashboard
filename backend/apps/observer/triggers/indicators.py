"""Derived technical indicators for the trigger DSL.

RSI/SMA/ATR delegate to apps.market.services.indicator.compute (single source
of indicator math); the rest are derived metrics. All return None on
insufficient/degenerate input — the evaluator treats None as a non-match.
"""

from __future__ import annotations

from apps.market.services.indicator import compute


def rsi(closes: list[float], period: int) -> float | None:
    return compute("RSI", closes, period=period)


def sma_spread_pct(closes: list[float], *, fast: int, slow: int) -> float | None:
    sf, ss = compute("SMA", closes, period=fast), compute("SMA", closes, period=slow)
    if sf is None or ss is None or ss == 0:
        return None
    return (sf - ss) / ss


def dist_from_sma_pct(closes: list[float], *, period: int, last: float) -> float | None:
    s = compute("SMA", closes, period=period)
    if s is None or s == 0:
        return None
    return (last - s) / s


def dist_from_high(highs: list[float], *, last: float) -> float | None:
    if not highs:
        return None
    hi = max(highs)
    return (last - hi) / hi if hi else None


def dist_from_low(lows: list[float], *, last: float) -> float | None:
    if not lows:
        return None
    lo = min(lows)
    return (last - lo) / lo if lo else None


def gap_pct(*, today_open: float, prev_close: float) -> float | None:
    if not prev_close:
        return None
    return (today_open - prev_close) / prev_close


def atr_pct(bars: list[dict], *, period: int, last: float) -> float | None:
    atr = compute("ATR", bars, period=period)
    if atr is None or not last:
        return None
    return atr / last


def indicator_value(
    metric: str,
    params: dict,
    *,
    closes: list[float],
    bars: list[dict],
    last: float | None,
    today_open: float | None = None,
    prev_close: float | None = None,
) -> float | None:
    """Metric -> indicator dispatch shared by the live metrics path and backtest
    replay, so the two cannot compute the same indicator differently.

    Guard order mirrors the original live path: the closes-only indicators
    (``rsi``/``sma_spread_pct``) tolerate a missing ``last``; everything else
    requires it. ``gap_pct`` needs the current bar's open and the prior close
    (``ind.gap_pct`` itself returns ``None`` on a zero/None prior close, so the
    backtest's old truthy guard and the live path's ``len(bars) < 2`` guard both
    collapse to passing ``None`` here).
    """
    if last is None and metric not in ("rsi", "sma_spread_pct"):
        return None
    if metric == "rsi":
        return rsi(closes, params["period"])
    if metric == "sma_spread_pct":
        return sma_spread_pct(closes, fast=params["fast"], slow=params["slow"])
    if last is None:
        return None
    if metric == "atr_pct":
        return atr_pct(bars, period=params["period"], last=last)
    if metric == "dist_from_sma_pct":
        return dist_from_sma_pct(closes, period=params["period"], last=last)
    if metric == "dist_from_52w_high":
        return dist_from_high([float(b["high"]) for b in bars], last=last)
    if metric == "dist_from_52w_low":
        return dist_from_low([float(b["low"]) for b in bars], last=last)
    if metric == "gap_pct":
        if today_open is None or prev_close is None:
            return None
        return gap_pct(today_open=today_open, prev_close=prev_close)
    return None
