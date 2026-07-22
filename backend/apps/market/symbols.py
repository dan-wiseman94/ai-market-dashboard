"""Symbol normalization for Schwab's index + futures symbology.

Schwab quotes cash indices under a ``$`` namespace (``$SPX``, ``$VIX``, ``$NDX``)
and futures under a leading-slash namespace (``/ES`` = continuous front-month
E-mini S&P 500). Bare user input ("SPX", "ES") matches neither: the quote/OHLC/
chain calls return an error envelope (quotes), empty candles (OHLC), or a 400
(chain) — *or worse*, silently resolve a colliding equity (bare "ES" is
Eversource Energy, "CL" is Colgate). Either way the snapshot is wrong. Map the
well-known index aliases and futures roots to their canonical Schwab symbols at
the fetch boundary so bare index/futures tickers "just work" everywhere —
quotes, OHLC, chain, and the chart image that renders off OHLC.

Cash-index aliases never collide with an equity/ETF. Futures roots *can* (CL =
Colgate, GC, NG, …); we intentionally resolve a bare root to the future to stay
consistent with ``calendar.heuristics`` (which classifies bare "ES" as a CME
future). A user who wants the colliding equity types it without ambiguity — but
the roots below are the futures intent. ETFs (SPY/QQQ) and ordinary equities
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

# Bare futures roots Schwab quotes under the leading-slash namespace (``/ES``).
# Single source of truth: ``calendar.heuristics`` imports these for market-key
# classification, so the symbol that gets fetched and the calendar it's read
# against can never disagree. Extend both behaviors by editing here only.
CME_FUTURE_ROOTS: frozenset[str] = frozenset(
    {"ES", "NQ", "RTY", "YM", "CL", "GC", "SI", "ZB", "ZN", "ZF", "NG", "HG"}
)
CFE_FUTURE_ROOTS: frozenset[str] = frozenset({"VX"})  # VIX future (≠ cash $VIX)
FUTURE_ROOTS: frozenset[str] = CME_FUTURE_ROOTS | CFE_FUTURE_ROOTS


def normalize_symbol(symbol: str) -> str:
    """Canonicalize a ticker for Schwab.

    Upper-cases, then maps bare cash-index aliases to their ``$``-prefixed symbol
    (``SPX`` -> ``$SPX``) and bare futures roots to their leading-slash symbol
    (``ES`` -> ``/ES``). Idempotent: already-prefixed symbols (``$SPX``, ``/ES``,
    a dated contract ``/ESU24``) pass through. Empty/whitespace input -> ``""``.
    """
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if s.startswith(("$", "/")):
        return s
    if s in INDEX_ALIASES:
        return INDEX_ALIASES[s]
    if s in FUTURE_ROOTS:
        return f"/{s}"
    return s


def is_equity_like(symbol: str) -> bool:
    """True when ``symbol`` is a plain stock/ETF suitable for equity-only providers
    (Finnhub company endpoints, SEC EDGAR). Futures (bare root or /-prefixed) and
    cash indices ($-prefixed or bare alias) resolve to instruments those providers
    either don't know or — worse — collide with an unrelated equity (bare "ES" is
    Eversource Energy on Finnhub while the rest of this app treats it as /ES)."""
    s = (symbol or "").strip().upper()
    if not s or s.startswith(("$", "/")):
        return False
    return s not in INDEX_ALIASES and s not in FUTURE_ROOTS
