"""Session state + open/closed checks, holiday- and half-day-aware."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime, timedelta

from django.utils import timezone

from apps.market.calendar.registry import get_market_calendar
from apps.market.calendar.resolve import calendar_for

log = logging.getLogger(__name__)

_LOOKAHEAD_DAYS = 16  # window for next_open / next_close search


@dataclass(frozen=True)
class MarketState:
    market_key: str
    phase: str  # open|closed|weekend|holiday|half_day|premarket|postmarket
    is_open: bool
    session_open: datetime | None
    session_close: datetime | None
    is_early_close: bool
    as_of: datetime | None  # most recent session close at/just before `at`
    next_open: datetime | None
    next_close: datetime | None

    def to_json(self) -> dict:
        def iso(v: datetime | None) -> str | None:
            return v.isoformat() if v else None

        return {
            "market_key": self.market_key,
            "phase": self.phase,
            "is_open": self.is_open,
            "session_open": iso(self.session_open),
            "session_close": iso(self.session_close),
            "is_early_close": self.is_early_close,
            "as_of": iso(self.as_of),
            "next_open": iso(self.next_open),
            "next_close": iso(self.next_close),
        }


def _resolve_market(symbol: str | None, market: str | None) -> str:
    if market:
        return market
    if symbol:
        return calendar_for(symbol)
    return "us_equity"


def market_state(
    *, symbol: str | None = None, market: str | None = None, at: datetime | None = None
) -> MarketState:
    now = at or timezone.now()
    market_key = _resolve_market(symbol, market)
    cal = get_market_calendar(market_key)

    # Some calendars (NYSE) define pre/post extended-hours sessions; pull those
    # columns when present so we can report premarket/postmarket. Calendars
    # without them (crypto, SIFMA, …) fall back to the plain regular schedule.
    has_ext = "pre" in cal.market_times and "post" in cal.market_times

    # Schedule over a window around `now`: robust across all calendars incl. 24/7
    # crypto, and the window means the UTC date never selects the wrong session.
    start = (now - timedelta(days=4)).date()
    end = (now + timedelta(days=_LOOKAHEAD_DAYS)).date()
    try:
        sched = (
            cal.schedule(start_date=start, end_date=end, start="pre", end="post")
            if has_ext
            else cal.schedule(start_date=start, end_date=end)
        )
    except Exception as exc:  # mcal can raise on odd ranges; treat as closed
        log.warning("market_state schedule failed for %s: %s", market_key, exc)
        return MarketState(market_key, "closed", False, None, None, False, None, None, None)

    today_open = today_close = None
    today_pre = today_post = None
    is_open_now = False
    is_early = False
    as_of = None
    next_open = next_close = None

    for _idx, row in sched.iterrows():
        o = row["market_open"].to_pydatetime()
        c = row["market_close"].to_pydatetime()
        if o.date() == now.date():
            today_open, today_close = o, c
            # A regular NYSE session is 6.5h; anything shorter is an early close.
            is_early = (c - o) < timedelta(hours=6, minutes=30)
            if has_ext:
                today_pre = row["pre"].to_pydatetime()
                today_post = row["post"].to_pydatetime()
        if o <= now <= c:
            is_open_now = True
        if c <= now and (as_of is None or c > as_of):
            as_of = c  # most recent session close at/before now
        if next_open is None and o > now:
            next_open = o
        if next_close is None and c > now:
            next_close = c

    if is_open_now:
        phase = "open"
    elif today_open is not None:
        # Regular session exists today but we're outside it: classify the
        # extended-hours windows when the calendar defines them, else closed.
        if today_pre is not None and today_pre <= now < today_open:
            phase = "premarket"
        elif today_post is not None and today_close is not None and today_close < now <= today_post:
            phase = "postmarket"
        else:
            phase = "half_day" if is_early else "closed"
    else:
        phase = "weekend" if now.weekday() >= 5 else "holiday"

    return MarketState(
        market_key=market_key,
        phase=phase,
        is_open=is_open_now,
        session_open=today_open,
        session_close=today_close,
        is_early_close=is_early,
        as_of=as_of,
        next_open=next_open,
        next_close=next_close,
    )


def is_open(
    *, symbol: str | None = None, market: str | None = None, at: datetime | None = None
) -> bool:
    return market_state(symbol=symbol, market=market, at=at).is_open


def add_trading_days(market: str, anchor: datetime, n: int) -> datetime:
    """Return `anchor` advanced by `n` trading sessions on `market`'s calendar.

    The returned datetime keeps `anchor`'s time-of-day but lands on the date of
    the n-th valid trading day at/after the next session. crypto counts daily.
    """
    cal = get_market_calendar(market)
    buffer_days = max(n * 3 + 10, 16)
    valid = cal.valid_days(
        start_date=anchor.date(), end_date=(anchor + timedelta(days=buffer_days)).date()
    )
    dates = [d.date() for d in valid]
    if not dates:
        return anchor + timedelta(days=n)
    base = 0
    for i, d in enumerate(dates):
        if d >= anchor.date():
            base = i
            break
    target_idx = min(base + n, len(dates) - 1)
    target = dates[target_idx]
    return datetime(
        target.year, target.month, target.day, anchor.hour, anchor.minute, tzinfo=anchor.tzinfo
    )


def session_close_on(market: str, on_date: _date) -> datetime | None:
    """The actual close (half-day-aware) for `market` on `on_date`, or None."""
    cal = get_market_calendar(market)
    try:
        sched = cal.schedule(start_date=on_date, end_date=on_date)
    except Exception as exc:
        log.warning("session_close_on failed for %s %s: %s", market, on_date, exc)
        return None
    if sched.empty:
        return None
    return sched.iloc[0]["market_close"].to_pydatetime()


def any_market_open(symbols: Iterable[str], at: datetime | None = None) -> bool:
    """True if any symbol's market is open. Empty -> us_equity check."""
    syms = [s for s in symbols if s]
    if not syms:
        return is_open(market="us_equity", at=at)
    # Resolve to distinct markets first so we call market_state once per market.
    markets = {calendar_for(s) for s in syms}
    return any(is_open(market=m, at=at) for m in markets)
