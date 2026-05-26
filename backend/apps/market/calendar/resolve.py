"""Resolve a bare ticker to a market key: override -> heuristic -> default.

The CalendarOverride lookup is added in Phase 2; until then this is
heuristic + default. Results are cached per-process and invalidated by
CalendarOverride.save()/delete() (wired in Phase 2).
"""

from __future__ import annotations

import logging

from apps.market.calendar.heuristics import classify

log = logging.getLogger(__name__)

_cache: dict[str, str] = {}


def clear_resolution_cache() -> None:
    _cache.clear()


def calendar_for(symbol: str) -> str:
    """Return the market key for a symbol. Never raises."""
    key = (symbol or "").strip().upper()
    if not key:
        return "us_equity"
    if key in _cache:
        return _cache[key]
    market = classify(key)
    _cache[key] = market
    return market
