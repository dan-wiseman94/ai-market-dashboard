"""Back-compat shim. Canonical service is apps.market.calendar.

Existing callers import is_market_open / market_status (NYSE). New code should
import from apps.market.calendar instead.
"""

from __future__ import annotations

from datetime import datetime

from apps.market.calendar import is_open as _is_open
from apps.market.calendar import market_state as _market_state


def is_market_open(at: datetime | None = None) -> bool:
    return _is_open(market="us_equity", at=at)


def market_status(at: datetime | None = None) -> dict:
    st = _market_state(market="us_equity", at=at)
    return {
        "is_open": st.is_open,
        "next_open": st.next_open,
        "next_close": st.next_close,
    }
