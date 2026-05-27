"""Best-effort macro seed used only when Finnhub's economic-calendar is unavailable.

Rows use the SAME shape as Finnhub `/calendar/economic` entries so `_upsert_macro`
handles both. These dates are best-effort and MUST be verified/refreshed against the
official calendars:
  - FOMC:        https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  - CPI / NFP:   https://www.bls.gov/schedule/news_release/
  - PCE / GDP:   https://www.bea.gov/news/schedule
Keep only high-impact US events. Time is UTC ("YYYY-MM-DD HH:MM:SS").
"""

from __future__ import annotations

# VERIFY these before relying on them in production; the live Finnhub pull upserts over them.
SEED_MACRO_EVENTS: list[dict] = [
    {
        "event": "FOMC Rate Decision",
        "country": "US",
        "impact": "high",
        "time": "2026-06-17 18:00:00",
        "estimate": None,
        "prev": None,
        "actual": None,
    },
    {
        "event": "CPI YoY",
        "country": "US",
        "impact": "high",
        "time": "2026-06-10 12:30:00",
        "estimate": None,
        "prev": None,
        "actual": None,
    },
    {
        "event": "Nonfarm Payrolls",
        "country": "US",
        "impact": "high",
        "time": "2026-06-05 12:30:00",
        "estimate": None,
        "prev": None,
        "actual": None,
    },
]
