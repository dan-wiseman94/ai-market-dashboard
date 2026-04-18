"""NYSE market-hours check for observer firings."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas_market_calendars as mcal
from django.utils import timezone

_NYSE = mcal.get_calendar("XNYS")  # cached at import time


def is_market_open(at: datetime | None = None) -> bool:
    """Half-day and holiday-aware NYSE regular-session check."""
    now = at or timezone.now()
    sched = _NYSE.schedule(start_date=now.date(), end_date=now.date())
    if sched.empty:
        return False
    open_t = sched.iloc[0]["market_open"].to_pydatetime()
    close_t = sched.iloc[0]["market_close"].to_pydatetime()
    return open_t <= now <= close_t


def market_status(at: datetime | None = None) -> dict:
    """Returns {is_open, next_open, next_close} for the bell tooltip + UI badge."""
    now = at or timezone.now()
    sched = _NYSE.schedule(
        start_date=now.date(),
        end_date=(now + timedelta(days=14)).date(),
    )
    is_open = False
    next_open = None
    next_close = None
    today = sched[sched.index.date == now.date()]
    if not today.empty:
        o = today.iloc[0]["market_open"].to_pydatetime()
        c = today.iloc[0]["market_close"].to_pydatetime()
        is_open = o <= now <= c
        if now < o:
            next_open = o
        if now < c:
            next_close = c
    if next_open is None:
        future = sched[sched["market_open"] > now]
        if not future.empty:
            next_open = future.iloc[0]["market_open"].to_pydatetime()
    return {"is_open": is_open, "next_open": next_open, "next_close": next_close}
