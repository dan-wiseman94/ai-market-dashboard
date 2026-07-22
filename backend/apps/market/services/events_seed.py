"""Best-effort macro seed used only when Finnhub's economic-calendar is unavailable.

The economic-calendar endpoint is a *premium* Finnhub product — a free-tier key
gets 403 every fetch — so in practice this seed is the only macro source unless
a paid key is configured. Rows use the SAME shape as Finnhub `/calendar/economic`
entries so `_upsert_macro` handles both. These dates are best-effort and MUST be
verified/refreshed against the official calendars before they lapse (once every
entry is in the past, `fetch_macro` logs a warning and every snapshot's macro
list goes empty):
  - FOMC:        https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  - CPI / NFP:   https://www.bls.gov/schedule/news_release/
  - PCE / GDP:   https://www.bea.gov/news/schedule
Keep only high-impact US events. Time is UTC ("YYYY-MM-DD HH:MM:SS"); 8:30 ET is
12:30 UTC during EDT and 13:30 UTC during EST, 14:00 ET is 18:00/19:00 UTC.
"""

from __future__ import annotations


def _row(event: str, time: str) -> dict:
    return {
        "event": event,
        "country": "US",
        "impact": "high",
        "time": time,
        "estimate": None,
        "prev": None,
        "actual": None,
    }


# VERIFY these before relying on them in production; the live Finnhub pull upserts over them.
SEED_MACRO_EVENTS: list[dict] = [
    # FOMC rate decisions (statement 14:00 ET on day 2 of the meeting).
    _row("FOMC Rate Decision", "2026-07-29 18:00:00"),
    _row("FOMC Rate Decision", "2026-09-16 18:00:00"),
    _row("FOMC Rate Decision", "2026-10-28 18:00:00"),
    _row("FOMC Rate Decision", "2026-12-09 19:00:00"),
    # CPI releases (08:30 ET).
    _row("CPI YoY", "2026-08-12 12:30:00"),
    _row("CPI YoY", "2026-09-11 12:30:00"),
    _row("CPI YoY", "2026-10-13 12:30:00"),
    _row("CPI YoY", "2026-11-10 13:30:00"),
    _row("CPI YoY", "2026-12-10 13:30:00"),
    # Nonfarm payrolls / Employment Situation (08:30 ET, first Friday).
    _row("Nonfarm Payrolls", "2026-08-07 12:30:00"),
    _row("Nonfarm Payrolls", "2026-09-04 12:30:00"),
    _row("Nonfarm Payrolls", "2026-10-02 12:30:00"),
    _row("Nonfarm Payrolls", "2026-11-06 13:30:00"),
    _row("Nonfarm Payrolls", "2026-12-04 13:30:00"),
]
