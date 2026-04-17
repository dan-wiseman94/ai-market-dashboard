"""Snapshot capture orchestration."""
from __future__ import annotations

from typing import Iterable

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.market.services.context import fetch_market_context
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


_FETCHERS = {
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
    "ohlc": lambda *, watchlist_tickers, ohlc_ticker=None, ohlc_timeframe="1m", ohlc_bars=60, **_: {
        "data": {
            "ticker": ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
            "timeframe": ohlc_timeframe,
            "bars": fetch_ohlc(
                ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
                timeframe=ohlc_timeframe, bars=ohlc_bars,
            ),
        },
    },
    "positions": lambda **_: {"data": fetch_positions()},
    "breadth": lambda **_: {"data": fetch_market_context()},
    "notes": lambda **_: {"data": {}},  # user notes live on Snapshot.notes; nothing to fetch
}


def _broadcast(snapshot_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"snapshot.{snapshot_id}",
        {"type": "snapshot_event", "payload": payload},
    )


def capture_for_existing(
    snap: Snapshot,
    *,
    watchlist_tickers: Iterable[str] = (),
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> Snapshot:
    """Fill in sections for an already-created Snapshot. Broadcasts progress over WS."""
    _broadcast(snap.id, {"event": "pending", "snapshot_id": snap.id, "includes": snap.includes})
    ok_count = 0

    for kind in snap.includes:
        fetcher = _FETCHERS.get(kind)
        section = SnapshotSection.objects.create(snapshot=snap, kind=kind, status="pending", payload={})
        _broadcast(snap.id, {"event": "section_started", "kind": kind})

        if fetcher is None:
            section.status = "failed"
            section.error = f"No fetcher for '{kind}'"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})
            continue

        try:
            result = fetcher(
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
            )
            section.payload = result["data"] or {}
            section.status = "done"
            section.save()
            ok_count += 1
            _broadcast(snap.id, {"event": "section_done", "kind": kind})
        except Exception as exc:  # noqa: BLE001
            section.status = "failed"
            section.error = f"{type(exc).__name__}: {exc}"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})

    snap.status = "ready" if ok_count > 0 else "failed"
    snap.save()
    _broadcast(snap.id, {"event": snap.status, "snapshot_id": snap.id})
    return snap


def capture(
    *,
    profile: TradingProfile,
    objective: str,
    includes: list[str],
    notes: str = "",
    source: str = "manual",
    watchlist_tickers: Iterable[str] = (),
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> Snapshot:
    """Create a Snapshot row and immediately fill it."""
    snap = Snapshot.objects.create(
        profile=profile, objective=objective, notes=notes,
        includes=includes, source=source, status="pending",
    )
    return capture_for_existing(
        snap,
        watchlist_tickers=watchlist_tickers,
        ohlc_ticker=ohlc_ticker,
        ohlc_timeframe=ohlc_timeframe,
        ohlc_bars=ohlc_bars,
    )
