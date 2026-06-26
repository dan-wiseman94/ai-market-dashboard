"""Celery wrappers around capture."""

from __future__ import annotations

from celery import shared_task

from apps.snapshots.models import Snapshot
from apps.snapshots.services import capture_for_existing


# At-most-once: capture is NOT idempotent (sections fetch/persist with side
# effects) and carries no compare-and-set claim, so it must override the global
# task_acks_late=True. A worker killed mid-capture leaves a visible partial
# snapshot the user can re-trigger — never a silently re-run double capture.
@shared_task(name="snapshots.capture", acks_late=False, reject_on_worker_lost=False)
def capture_task(
    *,
    snapshot_id: int,
    watchlist_tickers: list[str] | None = None,
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
    scenario: str | None = None,
) -> int:
    """Fill in sections for the given Snapshot id.

    ``scenario`` carries the E2E mock scenario from the web process; it lives in a
    ContextVar that does NOT cross into this worker, so re-apply it here to let
    MOCK_EXTERNAL capture honor service error-injection (e.g. ``news-503`` fails the
    news section). No-op in production, where nothing passes a scenario.
    """
    from apps.core.mocks import is_mock_mode, reset_scenario, set_scenario

    applied = bool(scenario) and is_mock_mode()
    if applied:
        set_scenario(scenario)  # type: ignore[arg-type]
    try:
        snap = Snapshot.objects.get(id=snapshot_id)
        capture_for_existing(
            snap,
            watchlist_tickers=watchlist_tickers or [],
            ohlc_ticker=ohlc_ticker,
            ohlc_timeframe=ohlc_timeframe,
            ohlc_bars=ohlc_bars,
        )
        return snap.id
    finally:
        if applied:
            reset_scenario()
