"""Market context: SPX/QQQ/VIX + sector ETFs + breadth (best-effort)."""

from __future__ import annotations

from apps.market import cache
from apps.market.services.quotes import fetch_quotes

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]
MACRO = {
    "10Y yield": "$TNX",
    "Dollar (UUP)": "UUP",
    "Oil (USO)": "USO",
    "Gold (GLD)": "GLD",
}
CORE = ["$SPX", "QQQ", "$VIX"]
# Advance/decline indices — Schwab may or may not return these; we try and fall back silently.
BREADTH = ["$ADVN", "$DECN", "$TICK", "$TRIN"]
CONTEXT_SYMBOLS = CORE + SECTOR_ETFS + BREADTH


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
    try:
        rs = intel.relative_strength(primary) if primary else None
        rotation = intel.sector_rotation()
    except Exception:
        rs = None
        rotation = []
    return {
        "spx_last": _last(quotes, "$SPX"),
        "qqq_last": _last(quotes, "QQQ"),
        "vix_last": _last(quotes, "$VIX"),
        "sectors": {etf: _last(quotes, etf) for etf in SECTOR_ETFS},
        "breadth": _internals(quotes),
        "relative_strength": rs,
        "sector_rotation": rotation,
    }
