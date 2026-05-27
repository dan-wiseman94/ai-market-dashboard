"""Symbol normalization for Schwab's index symbology.

Schwab quotes cash indices under a ``$`` namespace (``$SPX``, ``$VIX``, ``$NDX``)
that bare user input ("SPX", "VIX") never matches. The quote/OHLC/chain calls
then return an error envelope (quotes), empty candles (OHLC), or a 400 (chain),
so an index snapshot silently comes back empty. Map the well-known index
aliases to their canonical ``$``-prefixed Schwab symbols at the fetch boundary
so bare index tickers "just work" everywhere — quotes, OHLC, chain, and the
chart image that renders off OHLC.

Only unambiguous cash-index aliases are mapped; none of these collide with a
real equity or ETF ticker. ETFs (SPY/QQQ), sector ETFs, and ordinary equities
pass through untouched (just upper-cased).
"""

from __future__ import annotations

# Bare alias -> canonical Schwab symbol. Cash indices only.
INDEX_ALIASES: dict[str, str] = {
    "SPX": "$SPX",  # S&P 500 index
    "VIX": "$VIX",  # CBOE Volatility Index
    "NDX": "$NDX",  # Nasdaq-100 index
    "RUT": "$RUT",  # Russell 2000 index
    "DJI": "$DJI",  # Dow Jones Industrial Average
    "COMPX": "$COMPX",  # Nasdaq Composite index
    "OEX": "$OEX",  # S&P 100 index
}


def normalize_symbol(symbol: str) -> str:
    """Canonicalize a ticker for Schwab.

    Upper-cases, then maps bare cash-index aliases to their ``$``-prefixed Schwab
    symbol. Idempotent: already-prefixed symbols (``$SPX``) pass through. Empty or
    whitespace-only input returns ``""``.
    """
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if s.startswith("$"):
        return s
    return INDEX_ALIASES.get(s, s)
