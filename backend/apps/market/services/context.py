"""Market context: SPX/QQQ/VIX + sector ETFs + breadth (best-effort)."""

from __future__ import annotations

from apps.market import cache
from apps.market.services.quotes import fetch_quotes

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]
CORE = ["$SPX", "QQQ", "$VIX"]
# Advance/decline indices — Schwab may or may not return these; we try and fall back silently.
BREADTH = ["$ADVN", "$DECN", "$TICK", "$TRIN"]
CONTEXT_SYMBOLS = CORE + SECTOR_ETFS + BREADTH


def fetch_market_context() -> dict:
    return cache.get_or_fetch(
        "market:context",
        ttl_seconds=cache.ttl_for_kind("context"),
        fetcher=_fetch,
    )


def _last(quotes: dict, sym: str):
    return quotes.get(sym, {}).get("last")


def _fetch() -> dict:
    quotes = fetch_quotes(CONTEXT_SYMBOLS)
    return {
        "spx_last": _last(quotes, "$SPX"),
        "qqq_last": _last(quotes, "QQQ"),
        "vix_last": _last(quotes, "$VIX"),
        "sectors": {etf: _last(quotes, etf) for etf in SECTOR_ETFS},
        "breadth": {sym: v for sym in BREADTH if (v := _last(quotes, sym)) is not None},
    }
