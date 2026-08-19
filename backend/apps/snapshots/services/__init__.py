"""Snapshot capture orchestration."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

from apps.core.realtime import group_broadcast
from apps.market.calendar import calendar_for, market_state
from apps.market.services.chain import fetch_chain
from apps.market.services.context import fetch_market_context
from apps.market.services.edgar import fetch_filings as edgar_fetch_filings
from apps.market.services.events import upcoming_events
from apps.market.services.fred import fetch_macro as fred_fetch_macro
from apps.market.services.fundamentals import fetch_fundamentals
from apps.market.services.news import fetch_news
from apps.market.services.ohlc import (
    INTRADAY_TIMEFRAMES,
    fetch_ohlc,
    fetch_ohlc_24h,
)
from apps.market.services.overnight import overnight_board
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.market.services.safe_log import safe_err, scrub_secret_params
from apps.market.services.treasury import fetch_treasury
from apps.market.services.yields import live_yields
from apps.market.symbols import is_equity_like, normalize_symbol
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage, SnapshotSection
from apps.snapshots.primary import (
    primary_ticker as derive_primary_ticker,
)
from apps.snapshots.primary import (
    primary_ticker_from_quotes,
)
from apps.snapshots.services.render import render_chart_png
from apps.snapshots.token_budget import estimate_tokens

log = logging.getLogger(__name__)


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


def _fetch_chain_section(*, watchlist_tickers: list[str], **_) -> dict:
    # Schwab's chains endpoint serves equity and cash-index options but 400s on
    # futures symbols — pick the first non-futures watchlist symbol instead of
    # failing every futures-primary capture.
    for t in watchlist_tickers or ["SPY"]:
        if not normalize_symbol(t).startswith("/"):
            return {"data": fetch_chain(t)}
    raise ValueError(
        "no chain-capable symbol in watchlist (futures contracts have no equity option chain)"
    )


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
    # any_open over the SAME market set any_market_open() uses (falsy symbols
    # dropped; empty -> us_equity), read from the states we already computed rather
    # than recomputing every market's is_open a second time.
    syms = [t for t in tickers if t]
    open_markets = {calendar_for(t) for t in syms} if syms else {"us_equity"}
    return {
        "any_open": any(states[m]["is_open"] for m in open_markets),
        "markets": states,
    }


_WATCHLIST_DAILY_MAX_TICKERS = 8
_WATCHLIST_DAILY_BARS = 60


def _watchlist_daily_bars(watchlist_tickers: list[str], primary: str) -> dict[str, list[dict]]:
    """Compact daily history for the rest of the watchlist, so objectives that
    scan across names (breakout scans, relative strength) have a per-name price
    path — the primary ticker's intraday series alone can't answer them.
    Best-effort per ticker: one failing symbol never kills the section."""
    out: dict[str, list[dict]] = {}
    primary_norm = normalize_symbol(primary)
    for t in list(watchlist_tickers)[:_WATCHLIST_DAILY_MAX_TICKERS]:
        if normalize_symbol(t) == primary_norm:
            continue
        try:
            bars = fetch_ohlc(t, timeframe="1d", bars=_WATCHLIST_DAILY_BARS)
        except Exception as exc:
            log.warning("snapshots.ohlc.watchlist_daily skip %s: %s", t, safe_err(exc))
            continue
        if bars:
            out[t] = bars
    return out


def _fetch_ohlc_section(
    *,
    watchlist_tickers: list[str],
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
    **_,
) -> dict:
    ticker = _pick_ticker(ohlc_ticker, watchlist_tickers)
    watchlist_daily = _watchlist_daily_bars(list(watchlist_tickers), ticker)
    if ohlc_timeframe in INTRADAY_TIMEFRAMES:
        # Always the rolling last-24h window; a 1m request keeps only the newest
        # ~4h at 1m (never before the current session's open), earlier portion
        # coarsened to 5m (see apps.market.services.ohlc._FINE_WINDOW).
        bars = fetch_ohlc_24h(ticker, timeframe=ohlc_timeframe)
        data: dict = {"ticker": ticker, "timeframe": ohlc_timeframe, "bars": bars, "window": "24h"}
        if ohlc_timeframe == "1m":
            data["coarse_timeframe"] = "5m"
    else:
        # Daily: keep the fixed bar count (a 24h window of daily bars is a single bar).
        bars = fetch_ohlc(ticker, timeframe=ohlc_timeframe, bars=ohlc_bars)
        data = {"ticker": ticker, "timeframe": ohlc_timeframe, "bars": bars}
    if watchlist_daily:
        data["watchlist_daily"] = watchlist_daily
    return {"data": data}


def _fetch_news_section(*, watchlist_tickers: list[str], **_) -> dict:
    return {"data": {"items": fetch_news(list(watchlist_tickers))}}


_FETCHERS = {
    "breadth": lambda *, watchlist_tickers, **_: {
        "data": fetch_market_context(tickers=list(watchlist_tickers))
    },
    "chain": _fetch_chain_section,
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
    "fundamentals": lambda *, watchlist_tickers, **_: {
        "data": {t: fetch_fundamentals(t) for t in (list(watchlist_tickers) or [])[:8]},
    },
    "news": _fetch_news_section,
    "notes": lambda **_: {"data": {}},
    "ohlc": _fetch_ohlc_section,
    "overnight": lambda **_: {"data": overnight_board()},
    "positions": lambda **_: {"data": fetch_positions()},
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
    # Live CBOE yield-index quotes ride along because the FRED series lag a
    # business day — without them a Monday capture has no current yields at all.
    "macro": lambda **_: {"data": {"series": fred_fetch_macro(), "live_yields": live_yields()}},
    "filings": lambda *, watchlist_tickers, **_: {
        # Equity-like only — futures roots / indices aren't SEC filers, and a
        # bogus key ("NQ") in the payload reads as "no filings" to the AI.
        "data": {
            t: edgar_fetch_filings(t)
            for t in [s for s in list(watchlist_tickers) if is_equity_like(s)][:6]
        },
    },
    "treasury": lambda **_: {"data": fetch_treasury()},
}


def _broadcast(snapshot_id: int, payload: dict) -> None:
    group_broadcast(f"snapshot.{snapshot_id}", "snapshot_event", payload)


def _attach_client_captures(snap: Snapshot) -> bool:
    """Merge staged client-capture screenshots into the snapshot's ``image`` section.

    Client uploads are FK-attached to the Snapshot by ``SnapshotViewSet.create``
    but never enter ``payload["image_ids"]`` — the only ids the AI-delivery path
    (``apps.threads._request._snapshot_image_ids``) and the markdown serializer
    (``_render_image``) read. Without this merge, server-rendered charts would
    be delivered while user screenshots were silently dropped (the design
    intends both). The ``image`` section may not exist yet — the composer does not add
    ``"image"`` to ``includes`` just because a screenshot was staged — so create
    it when needed. Returns True when any client capture was attached.
    """
    client_ids = list(
        SnapshotImage.objects.filter(snapshot=snap, kind="client_capture")
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not client_ids:
        return False
    section, _ = SnapshotSection.objects.get_or_create(
        snapshot=snap, kind="image", defaults={"status": "done", "payload": {}}
    )
    existing = list((section.payload or {}).get("image_ids") or [])
    section.payload = {
        **(section.payload or {}),
        "image_ids": existing + [i for i in client_ids if i not in existing],
    }
    # A staged screenshot is deliverable even if the server render failed.
    section.status = "done"
    section.error = ""
    section.save(update_fields=["payload", "status", "error"])
    return True


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
    _primary: str | None = None

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
            if kind == "quotes" and _primary is None:
                _primary = primary_ticker_from_quotes(section.payload)
            ok_count += 1
            _broadcast(snap.id, {"event": "section_done", "kind": kind})
        except Exception as exc:
            section.status = "failed"
            # Provider errors can embed the full request URL — including a
            # query-string API key — so scrub before the text is persisted,
            # broadcast over WS, and rendered into the AI prompt as a stub.
            section.error = scrub_secret_params(f"{type(exc).__name__}: {exc}")
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})

    # Staged client screenshots are FK-attached pre-capture; fold them into the
    # image section so they actually reach the AI (not just the server render).
    attached_client_images = _attach_client_captures(snap)

    reps = _representative_tickers(snap, list(watchlist_tickers), ohlc_ticker)
    snap.market_state = _build_market_state(reps)
    snap.primary_ticker = derive_primary_ticker(snap) if _primary is None else _primary
    snap.status = "ready" if (ok_count > 0 or attached_client_images) else "failed"
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
