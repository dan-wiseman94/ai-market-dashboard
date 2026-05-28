"""OHLC price history service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from apps.market import cache
from apps.market.calendar import calendar_for, get_market_calendar
from apps.market.models import OHLCBar
from apps.market.schwab_client import get_schwab_client, schwab_json
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
    return cache.get_or_fetch(
        f"market:ohlc:{ticker}:{timeframe}:{bars}",
        ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
        fetcher=lambda: _fetch_from_schwab(ticker, timeframe, bars),
    )


def fetch_ohlc_session(ticker: str, *, timeframe: str, premarket_minutes: int = 60) -> list[dict]:
    """Intraday OHLC spanning the latest trading session plus `premarket_minutes`
    of premarket (default 1h), capped at "now" for mid-session captures.

    Use this for snapshot capture so the AI sees the whole day; ``fetch_ohlc``
    (fixed bar count, no extended hours) stays the path for charts and tools.
    """
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    return cache.get_or_fetch(
        f"market:ohlc:{ticker}:{timeframe}:session",
        ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
        fetcher=lambda: _fetch_session_from_schwab(ticker, timeframe, premarket_minutes),
    )


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
    """Upsert fetched bars into OHLCBar so trigger backtests have history to replay.

    Idempotent on the (ticker, timeframe, ts) unique constraint — re-fetching the
    same window updates values in place rather than duplicating rows.
    """
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
            log.warning("ohlc.persist.skip_bar ticker=%s ts=%s: %s", ticker, b.get("ts"), exc)
    if not rows:
        return
    OHLCBar.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["ticker", "timeframe", "ts"],
        update_fields=["open", "high", "low", "close", "volume"],
    )
