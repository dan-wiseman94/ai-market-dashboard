"""Quote fetching service."""
from __future__ import annotations

from typing import Iterable

from apps.market import cache
from apps.market.schwab_client import get_schwab_client


def fetch_quotes(tickers: Iterable[str]) -> dict[str, dict]:
    """Return {ticker: {last, bid, ask, volume, high, low, pct_change}} keyed by ticker.

    Cached in Redis for 5s. One Schwab call per cache miss; batched.
    """
    ticker_list = sorted(set(t.upper() for t in tickers if t))
    if not ticker_list:
        return {}
    cache_key = f"market:quotes:{','.join(ticker_list)}"
    return cache.get_or_fetch(
        cache_key,
        ttl_seconds=cache.ttl_for_kind("quotes"),
        fetcher=lambda: _fetch_from_schwab(ticker_list),
    )


def _fetch_from_schwab(tickers: list[str]) -> dict[str, dict]:
    client = get_schwab_client()
    resp = client.get_quotes(tickers)
    raw = resp.json()
    out: dict[str, dict] = {}
    for t, blob in raw.items():
        q = blob.get("quote", {}) if isinstance(blob, dict) else {}
        out[t] = {
            "last": q.get("lastPrice"),
            "bid": q.get("bidPrice"),
            "ask": q.get("askPrice"),
            "volume": q.get("totalVolume"),
            "high": q.get("highPrice"),
            "low": q.get("lowPrice"),
            "pct_change": q.get("netPercentChange"),
        }
    return out
