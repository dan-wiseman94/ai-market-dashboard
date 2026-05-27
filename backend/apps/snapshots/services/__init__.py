"""Snapshot capture orchestration."""

from __future__ import annotations

import json
from collections.abc import Iterable

from django.utils import timezone

from apps.core.realtime import group_broadcast
from apps.market.calendar import any_market_open, calendar_for, market_state
from apps.market.services.chain import fetch_chain
from apps.market.services.context import fetch_market_context
from apps.market.services.events import upcoming_events
from apps.market.services.news import fetch_news
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.services.render import render_chart_png
from apps.snapshots.token_budget import estimate_tokens


def stamp_payload_tokens(
    section: SnapshotSection,
    *,
    provider: str = "",
    model: str = "",
) -> None:
    """Count tokens in section.payload as JSON and persist to section.payload_tokens.

    Provider/model default to the snapshot's profile when available, so counts
    use the right tokenizer (e.g. Anthropic's count_tokens for Claude runs).
    """
    if not provider:
        profile = getattr(section.snapshot, "profile", None)
        if profile is not None:
            provider = profile.default_provider or "openai"
            model = model or profile.default_model or ""
    text = json.dumps(section.payload, default=str)
    tokens = estimate_tokens(text, provider=provider or "openai", model=model)
    section.payload_tokens = tokens
    section.save(update_fields=["payload_tokens"])


def _pick_ticker(ohlc_ticker: str | None, watchlist_tickers: list[str]) -> str:
    return ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY")


def _representative_tickers(
    snap: Snapshot, watchlist_tickers: list[str], ohlc_ticker: str | None
) -> list[str]:
    quotes = snap.sections.filter(kind="quotes", status="done").first()
    if quotes and isinstance(quotes.payload, dict) and quotes.payload:
        return [str(k) for k in quotes.payload]
    if watchlist_tickers:
        return list(watchlist_tickers)
    if ohlc_ticker:
        return [ohlc_ticker]
    return []


def _build_market_state(tickers: list[str]) -> dict:
    markets = {calendar_for(t) for t in tickers} or {"us_equity"}
    states = {m: market_state(market=m).to_json() for m in sorted(markets)}
    return {
        "captured_at": timezone.now().isoformat(),
        "any_open": any_market_open(tickers),
        "markets": states,
        "representative_tickers": list(tickers),
    }


def _fetch_ohlc_section(
    *,
    watchlist_tickers: list[str],
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
    **_,
) -> dict:
    ticker = _pick_ticker(ohlc_ticker, watchlist_tickers)
    return {
        "data": {
            "ticker": ticker,
            "timeframe": ohlc_timeframe,
            "bars": fetch_ohlc(ticker, timeframe=ohlc_timeframe, bars=ohlc_bars),
        }
    }


_FETCHERS = {
    "breadth": lambda **_: {"data": fetch_market_context()},
    "chain": lambda *, watchlist_tickers, **_: {
        "data": fetch_chain(_pick_ticker(None, watchlist_tickers)),
    },
    "image": lambda *, snapshot_id, watchlist_tickers, ohlc_ticker, ohlc_timeframe, ohlc_bars, **_: {
        "data": {
            "image_ids": [
                render_chart_png(
                    _pick_ticker(ohlc_ticker, watchlist_tickers),
                    ohlc_timeframe,
                    ohlc_bars,
                    snapshot_id=snapshot_id,
                ).id,
            ]
        },
    },
    "events": lambda *, watchlist_tickers, **_: {
        "data": upcoming_events(list(watchlist_tickers), within_days=14, include_macro=True),
    },
    "news": lambda *, watchlist_tickers, **_: {
        "data": {"items": fetch_news(list(watchlist_tickers))},
    },
    "notes": lambda **_: {"data": {}},
    "ohlc": _fetch_ohlc_section,
    "positions": lambda **_: {"data": fetch_positions()},
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
}


def _broadcast(snapshot_id: int, payload: dict) -> None:
    group_broadcast(f"snapshot.{snapshot_id}", "snapshot_event", payload)


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
        section = SnapshotSection.objects.create(
            snapshot=snap, kind=kind, status="pending", payload={}
        )
        _broadcast(snap.id, {"event": "section_started", "kind": kind})

        if fetcher is None:
            section.status = "failed"
            section.error = f"No fetcher for '{kind}'"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})
            continue

        try:
            result = fetcher(  # type: ignore[operator]
                snapshot_id=snap.id,
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
            )
            section.payload = result["data"] or {}
            section.status = "done"
            section.save()
            stamp_payload_tokens(section)
            ok_count += 1
            _broadcast(snap.id, {"event": "section_done", "kind": kind})
        except Exception as exc:
            section.status = "failed"
            section.error = f"{type(exc).__name__}: {exc}"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})

    reps = _representative_tickers(snap, list(watchlist_tickers), ohlc_ticker)
    snap.market_state = _build_market_state(reps)
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
        profile=profile,
        objective=objective,
        notes=notes,
        includes=includes,
        source=source,
        status="pending",
    )
    return capture_for_existing(
        snap,
        watchlist_tickers=watchlist_tickers,
        ohlc_ticker=ohlc_ticker,
        ohlc_timeframe=ohlc_timeframe,
        ohlc_bars=ohlc_bars,
    )
