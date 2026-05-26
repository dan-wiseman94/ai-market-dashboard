"""Maps logical market keys to pandas-market-calendars identifiers, cached."""

from __future__ import annotations

from functools import cache
from typing import Any

import pandas_market_calendars as mcal

# market_key -> mcal calendar id. Verify ids against the installed version with
# `mcal.get_calendar_names()` before relying on non-NYSE session behavior.
MARKETS: dict[str, str] = {
    "us_equity": "NYSE",
    "us_bond": "SIFMA_US",
    "cme_futures": "CME_Equity",
    "cfe_futures": "CFE",
    "crypto": "24/7",
    "lse": "LSE",
    "jpx": "JPX",
}

MARKET_CHOICES: list[tuple[str, str]] = [
    ("us_equity", "US equities (NYSE/NASDAQ)"),
    ("us_bond", "US bonds (SIFMA)"),
    ("cme_futures", "CME futures"),
    ("cfe_futures", "CFE / VIX futures"),
    ("crypto", "Crypto (24/7)"),
    ("lse", "London (LSE)"),
    ("jpx", "Tokyo (JPX)"),
]

DEFAULT_MARKET = "us_equity"


@cache
def get_market_calendar(market_key: str) -> Any:
    """Return the cached mcal calendar for a market key; unknown -> us_equity."""
    if market_key not in MARKETS:
        return get_market_calendar(DEFAULT_MARKET)
    return mcal.get_calendar(MARKETS[market_key])
