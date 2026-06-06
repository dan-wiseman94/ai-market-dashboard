"""Shared OHLCBar upsert for provider bar-fetchers.

Every provider that fetches OHLC (alpaca, twelvedata, tiingo, polygon, and the
Schwab `ohlc` path) had a byte-identical `_persist_bars` differing only by its
log prefix. This is the single implementation; each provider keeps a thin
`_persist_bars` delegator (so existing patch/import targets still resolve) that
passes its own `source` for the skip-bar log line.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from apps.market.models import OHLCBar

log = logging.getLogger(__name__)


def persist_bars(ticker: str, timeframe: str, bars: list[dict], *, source: str) -> None:
    """Idempotent upsert of fetched bars on the (ticker, timeframe, ts) unique
    constraint — re-fetching the same window updates values in place rather than
    duplicating rows. Malformed bars are skipped (logged under ``source``)."""
    rows: list[OHLCBar] = []
    for b in bars:
        try:
            if any(b.get(k) is None for k in ("open", "high", "low", "close", "volume", "ts")):
                continue
            rows.append(
                OHLCBar(
                    ticker=ticker,
                    timeframe=timeframe,
                    open=Decimal(str(b["open"])),
                    high=Decimal(str(b["high"])),
                    low=Decimal(str(b["low"])),
                    close=Decimal(str(b["close"])),
                    volume=int(b["volume"]),
                    ts=datetime.fromisoformat(b["ts"]),
                )
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            log.warning("%s.persist.skip_bar ticker=%s ts=%s: %s", source, ticker, b.get("ts"), exc)
    if not rows:
        return
    OHLCBar.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["ticker", "timeframe", "ts"],
        update_fields=["open", "high", "low", "close", "volume"],
    )
