"""OHLC price history service."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.market import cache
from apps.market.schwab_client import get_schwab_client

# Schwab exposes 30m bars; we map "1h" to that endpoint.
_METHOD_BY_TIMEFRAME = {
    "1m": "get_price_history_every_minute",
    "5m": "get_price_history_every_five_minutes",
    "15m": "get_price_history_every_fifteen_minutes",
    "1h": "get_price_history_every_thirty_minutes",
    "1d": "get_price_history_every_day",
}


def fetch_ohlc(ticker: str, *, timeframe: str, bars: int = 60) -> list[dict]:
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = ticker.upper()
    return cache.get_or_fetch(
        f"market:ohlc:{ticker}:{timeframe}:{bars}",
        ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
        fetcher=lambda: _fetch_from_schwab(ticker, timeframe, bars),
    )


def _fetch_from_schwab(ticker: str, timeframe: str, bars: int) -> list[dict]:
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    candles = method(ticker).json().get("candles", [])[-bars:]
    return [
        {
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
            "ts": datetime.fromtimestamp(c.get("datetime", 0) / 1000, tz=UTC).isoformat(),
        }
        for c in candles
    ]
