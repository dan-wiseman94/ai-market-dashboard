"""Resolve a bare ticker to a market key: override -> heuristic -> default.

A CalendarOverride row wins over the heuristic. Results are cached
per-process and invalidated by CalendarOverride.save()/delete().
"""

from __future__ import annotations

import logging

from apps.market.calendar.heuristics import classify

log = logging.getLogger(__name__)

_cache: dict[str, str] = {}


def clear_resolution_cache() -> None:
    _cache.clear()


def calendar_for(symbol: str) -> str:
    """Return the market key for a symbol: override -> heuristic -> default. Never raises."""
    key = (symbol or "").strip().upper()
    if not key:
        return "us_equity"
    if key in _cache:
        return _cache[key]
    market = _override_for(key) or classify(key)
    _cache[key] = market
    return market


def _override_for(symbol: str) -> str | None:
    # Lazy import: avoids AppRegistryNotReady at module load.
    from apps.market.models import CalendarOverride

    try:
        row = CalendarOverride.objects.filter(symbol=symbol).only("market_key").first()
    except Exception as exc:  # DB unavailable during some mgmt commands
        log.debug("override lookup skipped for %s: %s", symbol, exc)
        return None
    return row.market_key if row else None
