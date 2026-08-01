"""Live Treasury-yield reads from CBOE yield indices via the quotes path.

FRED's daily DGS* series publish through the H.15 release with a ~1-business-day
lag (a Monday-morning capture can only ever see Thursday's official yields). The
CBOE yield indices quote yield x 10 in real time — $TNX at 47.1 means 4.71% —
so dividing by 10 recovers percent. Best-effort: {} whenever index quotes are
unavailable (e.g. the free-provider fallback carries no index quotes).
"""

from __future__ import annotations

import logging

from apps.market.services.quotes import fetch_quotes
from apps.market.services.safe_log import safe_err

log = logging.getLogger(__name__)

# CBOE yield indices, quoted at yield x 10.
YIELD_INDICES: dict[str, str] = {
    "$IRX": "13W",
    "$FVX": "5Y",
    "$TNX": "10Y",
    "$TYX": "30Y",
}


def live_yields() -> dict:
    """{tenor: {"ticker", "yield_pct"}} for whichever CBOE yield indices quote."""
    try:
        quotes = fetch_quotes(list(YIELD_INDICES))
    except Exception as exc:
        log.warning("market.yields.quotes_unavailable: %s", safe_err(exc))
        return {}
    out: dict = {}
    for ticker, tenor in YIELD_INDICES.items():
        last = (quotes.get(ticker) or {}).get("last")
        if isinstance(last, int | float) and last > 0:
            out[tenor] = {"ticker": ticker, "yield_pct": round(last / 10, 3)}
    return out
