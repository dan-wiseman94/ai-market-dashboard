"""OHLC price history service."""
from __future__ import annotations

from datetime import datetime, timezone as dt_tz

from apps.market import cache
from apps.market.schwab_client import get_schwab_client

_METHOD_BY_TIMEFRAME = {
    "1m": "get_price_history_every_minute",
    "5m": "get_price_history_every_five_minutes",
    "15m": "get_price_history_every_fifteen_minutes",
    "1h": "get_price_history_every_thirty_minutes",  # Schwab exposes 30m; we map 1h to 30m here
    "1d": "get_price_history_every_day",
}


def fetch_ohlc(ticker: str, *, timeframe: str, bars: int = 60) -> list[dict]:
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = ticker.upper()
    cache_key = f"market:ohlc:{ticker}:{timeframe}:{bars}"
    return cache.get_or_fetch(
        cache_key,
        ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
        fetcher=lambda: _fetch_from_schwab(ticker, timeframe, bars),
    )


def _fetch_from_schwab(ticker: str, timeframe: str, bars: int) -> list[dict]:
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    resp = method(ticker)
    raw = resp.json()
    candles = raw.get("candles", [])[-bars:]
    out = []
    for c in candles:
        ts_ms = c.get("datetime", 0)
        out.append({
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
            "ts": datetime.fromtimestamp(ts_ms / 1000, tz=dt_tz.utc).isoformat(),
        })
    return out
