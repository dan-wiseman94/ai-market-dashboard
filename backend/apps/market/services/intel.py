"""Derived market intelligence: sector rotation, relative strength, IV summary.

Pure analytics composed from data the capture pipeline already fetches or
stores. Snapshot-agnostic; each public function returns a plain dict or None.
"""

from __future__ import annotations

from apps.market.services.context import SECTOR_ETFS
from apps.market.services.quotes import fetch_quotes

_SECTOR_NAMES = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Cons. Disc.",
    "XLP": "Cons. Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Comm. Svcs.",
}


def sector_rotation() -> dict | None:
    """Rank the 11 sector ETFs by today's % change (leaders → laggards)."""
    quotes = fetch_quotes(SECTOR_ETFS)
    ranked: list[dict] = []
    for etf in SECTOR_ETFS:
        pct = (quotes.get(etf) or {}).get("pct_change")
        if pct is None:
            continue
        ranked.append(
            {"etf": etf, "sector": _SECTOR_NAMES.get(etf, etf), "pct": round(float(pct), 2)}
        )
    if not ranked:
        return None
    ranked.sort(key=lambda r: r["pct"], reverse=True)
    return {"ranked": ranked}
