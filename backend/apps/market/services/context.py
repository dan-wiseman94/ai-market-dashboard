"""Market context: SPX/QQQ/VIX + sector ETFs + breadth (best-effort)."""

from __future__ import annotations

import logging

from apps.market import cache
from apps.market.services.quotes import fetch_quotes

log = logging.getLogger(__name__)

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]
MACRO = {
    "10Y yield": "$TNX",
    "Dollar (UUP)": "UUP",
    "Oil (USO)": "USO",
    "Gold (GLD)": "GLD",
}
CORE = ["$SPX", "QQQ", "$VIX"]
INDEX_COMPLEX = ["$SPX", "SPY", "QQQ"]
# Futures go in a SEPARATE quote call: Alpaca's fallback is one whole-batch
# request that returns {} for the entire batch when any symbol is rejected —
# a bad /ES must not blank the ETF rows.
FUTURES_COMPLEX = ["/ES", "/NQ"]
FACTOR_ETFS = ["MTUM", "VLUE", "QUAL", "USMV", "IWM", "SPY"]
# $UVOL/$DVOL ride the same try-and-see contract as the A/D indices.
BREADTH = ["$ADVN", "$DECN", "$TICK", "$TRIN", "$UVOL", "$DVOL"]
CONTEXT_SYMBOLS = [*CORE, "SPY", "UUP", *SECTOR_ETFS, *BREADTH]


def fetch_market_context(tickers: list[str] | None = None) -> dict:
    """Fetch and cache the market context.

    When *tickers* is provided, the first ticker is used as the primary for
    relative-strength computation.  The cache key is keyed by primary ticker
    so that snapshots for different tickers do not share RS data.
    """
    primary = (tickers[0].upper() if tickers else "") or ""
    cache_key = f"market:context:{primary}"
    return cache.get_or_fetch(
        cache_key,
        ttl_seconds=cache.ttl_for_kind("context"),
        fetcher=lambda: _fetch(primary or None),
    )


def _last(quotes: dict, sym: str):
    return quotes.get(sym, {}).get("last")


def _row(quotes: dict, sym: str) -> dict | None:
    q = quotes.get(sym) or {}
    if q.get("last") is None:
        return None
    return {"symbol": sym, "last": q.get("last"), "pct_change": q.get("pct_change")}


def _internals(quotes: dict) -> dict:
    """A/D internals, dropped wholesale while they're still warm-up placeholders.

    Before ~9:30 ET Schwab quotes the indices as near-zero values ($ADVN=8,
    $DECN=0, $TRIN=0.0) — passing those through reads as real breadth to the
    AI. A populated NYSE tape has thousands of advancing+declining issues, so
    a tiny A/D sum means "not yet populated", not "quiet market"."""
    internals = {sym: v for sym in BREADTH if (v := _last(quotes, sym)) is not None}
    advn = internals.get("$ADVN") or 0
    decn = internals.get("$DECN") or 0
    if advn + decn < 100:
        return {}
    return internals


def _fetch(primary: str | None = None) -> dict:
    from apps.market.services import intel

    quotes = fetch_quotes(CONTEXT_SYMBOLS)
    rs: dict | None = None
    rotation: list[dict] = []
    futures_quotes: dict = {}
    factor: dict | None = None
    stats: dict | None = None
    try:
        rs = intel.relative_strength(primary) if primary else None
    except Exception:
        log.warning("intel.relative_strength failed for %s", primary, exc_info=True)
        rs = None
    try:
        rotation = intel.sector_rotation()
    except Exception:
        log.warning("intel.sector_rotation failed", exc_info=True)
        rotation = []
    try:
        futures_quotes = fetch_quotes(FUTURES_COMPLEX)
    except Exception:
        log.warning("fetch_quotes failed for futures", exc_info=True)
        futures_quotes = {}
    try:
        factor = intel.factor_returns(FACTOR_ETFS)
    except Exception:
        log.warning("intel.factor_returns failed", exc_info=True)
        factor = None
    try:
        stats = intel.breadth_stats(SECTOR_ETFS)
    except Exception:
        log.warning("intel.breadth_stats failed", exc_info=True)
        stats = None
    return {
        "spx_last": _last(quotes, "$SPX"),
        "qqq_last": _last(quotes, "QQQ"),
        "vix_last": _last(quotes, "$VIX"),
        "sectors": {etf: _last(quotes, etf) for etf in SECTOR_ETFS},
        "breadth": _internals(quotes),
        "relative_strength": rs,
        "sector_rotation": rotation,
        "sector_pct": {
            etf: pc
            for etf in SECTOR_ETFS
            if (pc := quotes.get(etf, {}).get("pct_change")) is not None
        },
        "dollar": _row(quotes, "UUP"),
        "index_complex": [
            row
            for sym in INDEX_COMPLEX + FUTURES_COMPLEX
            if (row := _row({**quotes, **futures_quotes}, sym)) is not None
        ],
        "factor_returns": factor,
        "breadth_stats": stats,
    }
