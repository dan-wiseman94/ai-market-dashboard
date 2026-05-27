"""Quote fetching service."""

from __future__ import annotations

from collections.abc import Iterable

from apps.market import cache
from apps.market.schwab_client import get_schwab_client, schwab_json
from apps.market.symbols import normalize_symbol


def fetch_quotes(tickers: Iterable[str]) -> dict[str, dict]:
    """Return {ticker: {last, bid, ask, volume, high, low, pct_change}} keyed by ticker.

    Cached in Redis for 5s. One Schwab call per cache miss; batched. Index aliases
    (SPX, VIX, ...) are normalized to Schwab's ``$``-prefixed symbols before the call.
    """
    ticker_list = sorted({normalize_symbol(t) for t in tickers if t})
    if not ticker_list:
        return {}
    return cache.get_or_fetch(
        f"market:quotes:{','.join(ticker_list)}",
        ttl_seconds=cache.ttl_for_kind("quotes"),
        fetcher=lambda: _fetch_from_schwab(ticker_list),
    )


def _fetch_from_schwab(tickers: list[str]) -> dict[str, dict]:
    client = get_schwab_client()
    raw = schwab_json(client.get_quotes(tickers))
    out: dict[str, dict] = {}
    for t, blob in raw.items():
        # Schwab returns a top-level {"errors": {...}} envelope for unknown symbols;
        # skip anything without a real "quote" block so it isn't rendered as a ticker.
        if not isinstance(blob, dict) or "quote" not in blob:
            continue
        q = blob["quote"]
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
