"""Session state + open/closed checks, holiday- and half-day-aware."""

from __future__ import annotations

import logging
from dataclasses import dataclass
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

    # Plain schedule (no pre/post) over a window around `now`: robust across all
    # calendars incl. 24/7 crypto, and the window means the UTC date never
    # selects the wrong session.
    start = (now - timedelta(days=4)).date()
    end = (now + timedelta(days=_LOOKAHEAD_DAYS)).date()
    try:
        sched = cal.schedule(start_date=start, end_date=end)
    except Exception as exc:  # mcal can raise on odd ranges; treat as closed
        log.warning("market_state schedule failed for %s: %s", market_key, exc)
        return MarketState(market_key, "closed", False, None, None, False, None, None, None)

    today_open = today_close = None
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
        phase = "half_day" if is_early else "closed"  # session exists today, now outside it
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
