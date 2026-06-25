"""OHLC price history service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from django.utils import timezone

from apps.market import cache
from apps.market.calendar import calendar_for, get_market_calendar
from apps.market.schwab_client import (
    SchwabNotConnectedError,
    get_schwab_client,
    schwab_json,
)
from apps.market.services._bars import persist_bars
from apps.market.symbols import normalize_symbol

log = logging.getLogger(__name__)

# Schwab exposes 30m bars; we map "1h" to that endpoint.
_METHOD_BY_TIMEFRAME = {
    "1m": "get_price_history_every_minute",
    "5m": "get_price_history_every_five_minutes",
    "15m": "get_price_history_every_fifteen_minutes",
    "1h": "get_price_history_every_thirty_minutes",
    "1d": "get_price_history_every_day",
}

# Intraday timeframes for which "full session + premarket" is meaningful; daily
# keeps the fixed bar-count behavior.
SESSION_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h"})


def fetch_ohlc(ticker: str, *, timeframe: str, bars: int = 60) -> list[dict]:
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    try:
        return cache.get_or_fetch(
            f"market:ohlc:{ticker}:{timeframe}:{bars}",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_from_schwab(ticker, timeframe, bars),
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_bars(ticker, timeframe, limit=bars)
        if alt is None:
            raise
        return alt


def fetch_ohlc_session(ticker: str, *, timeframe: str, premarket_minutes: int = 60) -> list[dict]:
    """Intraday OHLC spanning the latest trading session plus `premarket_minutes`
    of premarket (default 1h), capped at "now" for mid-session captures.

    Use this for snapshot capture so the AI sees the whole day; ``fetch_ohlc``
    (fixed bar count, no extended hours) stays the path for charts and tools.
    """
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    try:
        return cache.get_or_fetch(
            f"market:ohlc:{ticker}:{timeframe}:session",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_session_from_schwab(ticker, timeframe, premarket_minutes),
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_bars(ticker, timeframe, limit=120)
        if alt is None:
            raise
        return alt


def fetch_ohlc_overnight(ticker: str, *, timeframe: str) -> list[dict]:
    """Intraday OHLC spanning the prior session's open through now, extended hours
    included and never clamped to the regular close.

    For a pre-market capture this yields one continuous series: the prior regular
    session + after-hours + overnight + this morning's pre-market. Use this for
    overnight-mode snapshot capture only.
    """
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    try:
        return cache.get_or_fetch(
            f"market:ohlc:{ticker}:{timeframe}:overnight",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_overnight_from_schwab(ticker, timeframe),
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_bars(ticker, timeframe, limit=200)
        if alt is None:
            raise
        return alt


def _overnight_window(
    ticker: str, *, at: datetime | None = None
) -> tuple[datetime, datetime] | None:
    """(start, now) UTC: start = the regular open of the most-recently-closed
    session at/before `at`; end = `at`. None when no session falls in the lookback.
    """
    now = at or timezone.now()
    cal = get_market_calendar(calendar_for(ticker))
    try:
        sched = cal.schedule(
            start_date=(now - timedelta(days=7)).date(),
            end_date=(now + timedelta(days=1)).date(),
        )
    except Exception as exc:  # mcal can raise on odd ranges; treat as no data
        log.warning("ohlc.overnight_window schedule failed for %s: %s", ticker, exc)
        return None
    start = None
    for _idx, row in sched.iterrows():
        if row["market_close"].to_pydatetime() <= now:  # latest session already closed
            start = row["market_open"].to_pydatetime()
    if start is None:
        return None
    return start, now


def _fetch_overnight_from_schwab(ticker: str, timeframe: str) -> list[dict]:
    window = _overnight_window(ticker)
    if window is None:
        return _fetch_session_from_schwab(ticker, timeframe, 60)
    start_dt, end_dt = window
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    candles = schwab_json(
        method(
            ticker,
            start_datetime=start_dt,
            end_datetime=end_dt,
            need_extended_hours_data=True,
        )
    ).get("candles", [])
    rows = [
        r
        for r in _rows_from_candles(candles)
        if start_dt <= datetime.fromisoformat(r["ts"]) <= end_dt
    ]
    _persist_bars(ticker, timeframe, rows)
    return rows


def _rows_from_candles(candles: list[dict]) -> list[dict]:
    return [
        {
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
            "ts": datetime.fromtimestamp(c.get("datetime", 0) / 1000, tz=UTC).isoformat(),
        }
        for c in candles
    ]


def _most_recent_session_open(ticker: str, *, at: datetime) -> datetime | None:
    """Regular open of the latest session that has opened at/before `at`. None when
    no session falls in the 7-day lookback (calendar failure / empty schedule)."""
    cal = get_market_calendar(calendar_for(ticker))
    try:
        sched = cal.schedule(
            start_date=(at - timedelta(days=7)).date(),
            end_date=(at + timedelta(days=1)).date(),
        )
    except Exception as exc:  # mcal can raise on odd ranges; treat as no data
        log.warning("ohlc.session_open schedule failed for %s: %s", ticker, exc)
        return None
    chosen = None
    for _idx, row in sched.iterrows():
        o = row["market_open"].to_pydatetime()
        if o <= at:  # keep the latest session already opened
            chosen = o
    return chosen


def _union_window(
    ticker: str, *, at: datetime | None = None
) -> tuple[datetime, datetime, datetime] | None:
    """(start, end, session_open) for the rolling 24h window, never thinner than the
    current session: start = min(at - 24h, session_open); end = at. None when no
    session falls in the lookback."""
    now = at or timezone.now()
    session_open = _most_recent_session_open(ticker, at=now)
    if session_open is None:
        return None
    start = min(now - timedelta(hours=24), session_open)
    return start, now, session_open


def _session_window(
    ticker: str, *, premarket_minutes: int, at: datetime | None = None
) -> tuple[datetime, datetime] | None:
    """(start, end) UTC for the latest session that has opened at/before `at`.

    Extends `premarket_minutes` before the regular open and caps the end at `at`
    so an intraday capture stops at "now". On weekends/holidays this resolves to
    the most recent completed session. None when no session falls in the lookback.
    """
    now = at or timezone.now()
    cal = get_market_calendar(calendar_for(ticker))
    try:
        sched = cal.schedule(
            start_date=(now - timedelta(days=7)).date(),
            end_date=(now + timedelta(days=1)).date(),
        )
    except Exception as exc:  # mcal can raise on odd ranges; treat as no data
        log.warning("ohlc.session_window schedule failed for %s: %s", ticker, exc)
        return None
    chosen_open = chosen_close = None
    for _idx, row in sched.iterrows():
        o = row["market_open"].to_pydatetime()
        c = row["market_close"].to_pydatetime()
        if o <= now:  # keep the latest session already opened
            chosen_open, chosen_close = o, c
    if chosen_open is None or chosen_close is None:
        return None
    return chosen_open - timedelta(minutes=premarket_minutes), min(chosen_close, now)


def _fetch_session_from_schwab(ticker: str, timeframe: str, premarket_minutes: int) -> list[dict]:
    window = _session_window(ticker, premarket_minutes=premarket_minutes)
    if window is None:
        return []
    start_dt, end_dt = window
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    candles = schwab_json(
        method(
            ticker,
            start_datetime=start_dt,
            end_datetime=end_dt,
            need_extended_hours_data=True,
        )
    ).get("candles", [])
    # Schwab honors the window loosely; clamp to it so we don't bleed into the
    # prior session's post-market or the next premarket.
    rows = [
        r
        for r in _rows_from_candles(candles)
        if start_dt <= datetime.fromisoformat(r["ts"]) <= end_dt
    ]
    _persist_bars(ticker, timeframe, rows)
    return rows


def _fetch_from_schwab(ticker: str, timeframe: str, bars: int) -> list[dict]:
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    candles = schwab_json(method(ticker)).get("candles", [])[-bars:]
    rows = _rows_from_candles(candles)
    _persist_bars(ticker, timeframe, rows)
    return rows


def _persist_bars(ticker: str, timeframe: str, bars: list[dict]) -> None:
    """Upsert fetched bars into OHLCBar so trigger backtests have history to replay."""
    persist_bars(ticker, timeframe, bars, source="ohlc")
