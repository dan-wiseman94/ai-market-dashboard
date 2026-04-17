"""Market context: SPY/QQQ/VIX + sector ETFs + breadth (best-effort)."""
from __future__ import annotations

from apps.market import cache
from apps.market.services.quotes import fetch_quotes

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]
CORE = ["SPY", "QQQ", "$VIX"]
# Advance/decline indices — Schwab may or may not return these; we try and fall back silently.
BREADTH = ["$ADVN", "$DECN", "$TICK", "$TRIN"]
CONTEXT_SYMBOLS = CORE + SECTOR_ETFS + BREADTH


def fetch_market_context() -> dict:
    return cache.get_or_fetch(
        "market:context",
        ttl_seconds=cache.ttl_for_kind("context"),
        fetcher=_fetch,
    )


def _fetch() -> dict:
    quotes = fetch_quotes(CONTEXT_SYMBOLS)
    sectors = {etf: quotes.get(etf, {}).get("last") for etf in SECTOR_ETFS}
    breadth = {}
    for sym in BREADTH:
        q = quotes.get(sym, {})
        if q.get("last") is not None:
            breadth[sym] = q["last"]
    return {
        "spy_last": quotes.get("SPY", {}).get("last"),
        "qqq_last": quotes.get("QQQ", {}).get("last"),
        "vix_last": quotes.get("$VIX", {}).get("last"),
        "sectors": sectors,
        "breadth": breadth,
    }
