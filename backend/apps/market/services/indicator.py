"""Pure indicator math. No I/O; caller fetches closes via fetch_ohlc() first.

Signatures intentionally narrow — SMA/EMA/RSI take `list[float]` of closes;
ATR takes `list[dict]` with high/low/close keys (matching fetch_ohlc's bar shape).
"""
from __future__ import annotations


def compute(name: str, data: list, *, period: int) -> float | None:
    name = name.upper()
    if name == "SMA":
        return _sma(data, period)
    if name == "EMA":
        return _ema(data, period)
    if name == "RSI":
        return _rsi(data, period)
    if name == "ATR":
        return _atr(data, period)
    raise ValueError(f"Unknown indicator: {name!r}")


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _rsi(closes: list[float], period: int) -> float | None:
    if len(closes) <= period:
        return None
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(bars: list[dict], period: int) -> float | None:
    if len(bars) < 2:
        return None
    trs: list[float] = []
    prev_close = bars[0].get("close")
    for bar in bars[1:]:
        h, low, c = float(bar["high"]), float(bar["low"]), float(bar["close"])
        tr = (
            max(h - low, abs(h - prev_close), abs(low - prev_close))
            if prev_close is not None
            else h - low
        )
        trs.append(tr)
        prev_close = c
    if not trs:
        return None
    window = trs[-period:]
    return sum(window) / len(window)
