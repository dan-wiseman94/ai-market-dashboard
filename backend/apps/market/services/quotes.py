"""Quote fetching service."""

from __future__ import annotations

from collections.abc import Iterable

from apps.market import cache
from apps.market.schwab_client import (
    SchwabNotConnectedError,
    get_schwab_client,
    schwab_json,
)
from apps.market.symbols import normalize_symbol


def fetch_quotes(tickers: Iterable[str], *, gap_context: bool = False) -> dict[str, dict]:
    """Return {ticker: {last, bid, ask, volume, high, low, pct_change}} keyed by ticker.

    With ``gap_context=True`` each value also carries ``prior_close``, ``regular_last``,
    ``mark``, ``security_status`` and a computed ``gap_pct`` — for pre-market reads.
    Cached in Redis for 5s (separate key per gap/non-gap so payloads don't collide).
    """
    ticker_list = sorted({normalize_symbol(t) for t in tickers if t})
    if not ticker_list:
        return {}
    suffix = ":gap" if gap_context else ""
    try:
        return cache.get_or_fetch(
            f"market:quotes:{','.join(ticker_list)}{suffix}",
            ttl_seconds=cache.ttl_for_kind("quotes"),
            fetcher=lambda: _fetch_from_schwab(ticker_list, gap_context=gap_context),
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_quotes(ticker_list)
        if alt is None:
            raise
        return alt


def _fetch_from_schwab(tickers: list[str], *, gap_context: bool = False) -> dict[str, dict]:
    client = get_schwab_client()
    raw = schwab_json(client.get_quotes(tickers))
    out: dict[str, dict] = {}
    for t, blob in raw.items():
        if not isinstance(blob, dict) or "quote" not in blob:
            continue
        q = blob["quote"]
        row = {
            "last": q.get("lastPrice"),
            "bid": q.get("bidPrice"),
            "ask": q.get("askPrice"),
            "volume": q.get("totalVolume"),
            "high": q.get("highPrice"),
            "low": q.get("lowPrice"),
            "pct_change": q.get("netPercentChange"),
        }
        if gap_context:
            reg = blob.get("regular") or {}
            prior_close = q.get("closePrice")
            last = row["last"]
            gap_pct = None
            if (
                isinstance(prior_close, int | float)
                and prior_close
                and isinstance(last, int | float)
            ):
                gap_pct = (last - prior_close) / prior_close * 100
            row.update(
                {
                    "prior_close": prior_close,
                    "regular_last": reg.get("regularMarketLastPrice"),
                    "mark": q.get("mark"),
                    "security_status": q.get("securityStatus"),
                    "gap_pct": gap_pct,
                }
            )
        out[t] = row
    return out
