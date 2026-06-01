"""Gather the deterministic briefing sections. Defensive: a failing section degrades to empty."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from apps.market.services.events import upcoming_events
from apps.market.services.news import fetch_news
from apps.market.services.quotes import fetch_quotes
from apps.profiles.models import TradingProfile, WatchlistSymbol
from apps.snapshots.services import capture
from apps.thesis.models import Thesis
from apps.triggers.models import TriggerFiring
from apps.triggers.services.describe import describe

log = logging.getLogger(__name__)


def _watchlist_union() -> list[str]:
    return list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())


def _pct_move(current, level) -> float | None:
    if current is None or level is None:
        return None
    c = float(current)
    if c == 0:
        return None
    return round((float(level) - c) / c * 100, 2)


def _theses_section() -> list[dict]:
    theses = list(Thesis.objects.filter(status="open"))
    if not theses:
        return []
    tickers = sorted({t.ticker for t in theses})
    try:
        quotes = fetch_quotes(tickers)
    except Exception as exc:
        log.warning("briefing.theses.quotes_failed: %s", exc)
        quotes = {}
    out: list[dict] = []
    for t in theses:
        current = (quotes.get(t.ticker) or {}).get("last")
        out.append(
            {
                "id": t.id,
                "ticker": t.ticker,
                "direction": t.direction,
                "conviction": t.conviction,
                "entry": float(t.entry_price) if t.entry_price is not None else None,
                "target": float(t.target_price) if t.target_price is not None else None,
                "invalidation": float(t.invalidation_price)
                if t.invalidation_price is not None
                else None,
                "current": float(current) if current is not None else None,
                "pct_to_target": _pct_move(current, t.target_price),
                "pct_to_invalidation": _pct_move(current, t.invalidation_price),
            }
        )
    return out


def _since() -> datetime:
    from apps.briefing.models import BriefingRun

    prev = BriefingRun.objects.filter(status="ready").order_by("-created_at").first()
    return prev.created_at if prev else timezone.now() - timedelta(hours=24)


def _triggers_section(since: datetime) -> list[dict]:
    rows = (
        TriggerFiring.objects.filter(fired_at__gte=since)
        .select_related("trigger")
        .order_by("-fired_at")
    )
    out: list[dict] = []
    for f in rows:
        name = getattr(f.trigger, "name", None) or str(f.trigger)
        out.append(
            {
                "trigger_id": f.trigger_id,
                "name": name,
                "fired_at": f.fired_at.isoformat(),
                "summary": describe(f.matched_values),
            }
        )
    return out


def _news_section(tickers: list[str], lookback_hours: int) -> list[dict]:
    try:
        items = fetch_news(tickers, lookback_hours=lookback_hours)
    except Exception as exc:
        log.warning("briefing.news_failed: %s", exc)
        return []
    return [
        {
            "headline": it.get("headline"),
            "source": it.get("source"),
            "url": it.get("url"),
            "published_at": it.get("datetime"),
            "ticker": it.get("related", ""),
        }
        for it in items[:15]
    ]


def _capture_market(profile, tickers: list[str]):
    """Capture a breadth-only snapshot; return (snapshot, market_dict). Defensive."""
    if profile is None:
        return None, {}
    try:
        snap = capture(
            profile=profile,
            objective="Morning briefing market context",
            includes=["breadth"],
            source="briefing",
            watchlist_tickers=tickers,
        )
    except Exception as exc:
        log.warning("briefing.market_capture_failed: %s", exc)
        return None, {}
    sec = snap.sections.filter(kind="breadth", status="done").first()
    return snap, (sec.payload if sec else {})


def _book_section() -> dict:
    from apps.book.services.compute import current_book

    snap = current_book()
    if snap is None:
        return {"concentration": None, "regime_fit": None, "top_risk": None}
    return {
        "concentration": snap.concentration or None,
        "regime_fit": snap.regime_fit or None,
        "top_risk": snap.narrative or None,
    }


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:
        log.warning("briefing.section_failed: %s", exc)
        return default


def assemble(config) -> tuple[dict, object | None]:
    tickers = _safe(_watchlist_union, [])
    since = _safe(_since, timezone.now() - timedelta(hours=24))
    profile = _safe(lambda: config.profile or TradingProfile.objects.first(), config.profile)
    snapshot, market = _capture_market(profile, tickers)
    data = {
        "theses": _safe(_theses_section, []),
        "events": _safe(
            lambda: upcoming_events(tickers, within_days=config.events_within_days),
            {"earnings": [], "macro": []},
        ),
        "triggers": _safe(lambda: _triggers_section(since), []),
        "news": _safe(lambda: _news_section(tickers, config.news_lookback_hours), []),
        "market": market,
        "since": since.isoformat(),
        "book": _safe(_book_section, {"concentration": None, "regime_fit": None, "top_risk": None}),
    }
    return data, snapshot
