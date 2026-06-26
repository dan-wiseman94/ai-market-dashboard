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

# Intraday timeframes for which the rolling 24h window is meaningful; daily keeps
# the fixed bar-count behavior.
INTRADAY_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h"})

# A 1m request keeps the current session at 1m and coarsens the older part of the
# 24h window to this (24h of 1m extended-hours bars is too many).
_COARSE_TIMEFRAME = "5m"

# Free-provider fallback is count-based and single-resolution; size ~24h per timeframe.
_ALT_24H_LIMIT = {"1m": 480, "5m": 288, "15m": 96, "1h": 48}


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


def fetch_ohlc_24h(ticker: str, *, timeframe: str) -> list[dict]:
    """Intraday OHLC over a rolling 24h window, never thinner than the current
    session (start = min(now-24h, session_open); end = now), extended hours
    included. A 1m request keeps the current session at 1m and coarsens the older
    portion of the window to 5m. Use this for snapshot capture; ``fetch_ohlc``
    (fixed count) stays the path for charts and tools.
    """
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    try:
        return cache.get_or_fetch(
            f"market:ohlc:{ticker}:{timeframe}:24h",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_24h_from_schwab(ticker, timeframe),
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_bars(ticker, timeframe, limit=_ALT_24H_LIMIT.get(timeframe, 288))
        if alt is None:
            raise
        return alt


def _fetch_window_from_schwab(
    ticker: str, timeframe: str, start_dt: datetime, end_dt: datetime
) -> list[dict]:
    """Fetch one resolution over [start_dt, end_dt] with extended hours, clamp rows
    to the window (Schwab honors it loosely), persist, and return rows."""
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


def _fetch_24h_from_schwab(ticker: str, timeframe: str) -> list[dict]:
    window = _union_window(ticker)
    if window is None:
        return []
    start_dt, end_dt, session_open = window
    if timeframe != "1m" or session_open <= start_dt:
        # Non-1m, or no older portion (weekend / pre-market): single resolution.
        return _fetch_window_from_schwab(ticker, timeframe, start_dt, end_dt)
    # 1m request: coarsen the pre-session portion to 5m, keep the current session at 1m.
    older = [
        b
        for b in _fetch_window_from_schwab(ticker, _COARSE_TIMEFRAME, start_dt, session_open)
        if datetime.fromisoformat(b["ts"]) < session_open  # drop the boundary bar (belongs to 1m)
    ]
    recent = _fetch_window_from_schwab(ticker, "1m", session_open, end_dt)
    return older + recent


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
