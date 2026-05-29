"""Overnight board: index futures + vol/rates + overseas cash indices.

Reuses the breadth pattern — fetch a curated symbol set in one batched call and
silently drop any symbol Schwab won't quote. Overseas-index symbology on Schwab
is partial; unresolved symbols just don't appear in the board.
"""

from __future__ import annotations

from apps.market.services.quotes import fetch_quotes

US_INDEX_FUTURES = ["/ES", "/NQ", "/YM", "/RTY"]
VOL_RATES = ["/VX", "/ZN"]
# Best-effort overseas cash indices; verify/adjust symbols against live Schwab
# responses. Unresolved symbols are dropped (see module docstring).
OVERSEAS = ["$NIKK", "$HSI", "$UKX", "$DAX", "$SX5E"]


def overnight_board() -> dict:
    """{"futures": {...}, "vol_rates": {...}, "overseas": {...}} keyed by symbol,
    each value a gap-context quote dict. Missing symbols are omitted."""
    quotes = fetch_quotes(US_INDEX_FUTURES + VOL_RATES + OVERSEAS, gap_context=True)

    def group(symbols: list[str]) -> dict:
        return {s: quotes[s] for s in symbols if s in quotes}

    return {
        "futures": group(US_INDEX_FUTURES),
        "vol_rates": group(VOL_RATES),
        "overseas": group(OVERSEAS),
    }
