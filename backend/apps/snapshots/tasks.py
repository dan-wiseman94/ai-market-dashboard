"""Celery wrappers around capture."""

from __future__ import annotations

from celery import shared_task

from apps.snapshots.models import Snapshot
from apps.snapshots.services import capture_for_existing


@shared_task(name="snapshots.capture")
def capture_task(
    *,
    snapshot_id: int,
    watchlist_tickers: list[str] | None = None,
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> int:
    """Fill in sections for the given Snapshot id."""
    snap = Snapshot.objects.get(id=snapshot_id)
    capture_for_existing(
        snap,
        watchlist_tickers=watchlist_tickers or [],
        ohlc_ticker=ohlc_ticker,
        ohlc_timeframe=ohlc_timeframe,
        ohlc_bars=ohlc_bars,
    )
    return snap.id
