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
    if sf is None or ss in (None, 0):
        return None
    return (sf - ss) / ss


def dist_from_sma_pct(closes: list[float], *, period: int, last: float) -> float | None:
    s = compute("SMA", closes, period=period)
    if s in (None, 0):
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
