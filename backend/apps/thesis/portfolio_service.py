"""Portfolio P&L services — pure, read-only over OHLCBar via apps.market.returns.

No broker write path. All functions are defensive: a missing OHLC bar returns
None fields rather than raising. Short-position convention:

    sign = +1 for long, -1 for short

    unrealized_pnl = (last - avg_cost) * quantity * sign
    market_value   = last * quantity          (absolute exposure; same for long/short)

For a short: the position profits when the price *falls*, so the sign inversion
makes (last < avg_cost) → positive pnl. market_value is the current cost to
close (buy-to-cover) at the mark; cost_basis is what was received on the open.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from apps.market.returns import nearest_bar_close


def unrealized_pnl(position) -> dict:  # type: ignore[type-arg]
    """Mark-to-market P&L for an OPEN position using the latest stored OHLC close.

    Returns a dict with keys:
    - ``last``            float | None  — latest bar close price
    - ``market_value``    float | None  — last * quantity (absolute exposure)
    - ``unrealized_pnl``  float | None  — P&L vs cost basis, sign-corrected for direction
    - ``unrealized_pct``  float | None  — unrealized_pnl / cost_basis * 100

    All computed fields are None when no bar is available (honest coverage gap).
    Never raises.
    """
    try:
        last = nearest_bar_close(position.ticker, timezone.now())
    except Exception:
        last = None

    if last is None:
        return {
            "last": None,
            "market_value": None,
            "unrealized_pnl": None,
            "unrealized_pct": None,
        }

    avg_cost = float(position.avg_cost)
    quantity = float(position.quantity)
    sign = -1.0 if position.direction == "short" else 1.0

    cost_basis = avg_cost * quantity
    market_value = last * quantity
    upnl = (last - avg_cost) * quantity * sign
    upct = (upnl / cost_basis * 100.0) if cost_basis != 0 else None

    return {
        "last": last,
        "market_value": market_value,
        "unrealized_pnl": upnl,
        "unrealized_pct": upct,
    }


def realized_pnl(
    *,
    avg_cost: Decimal,
    close_price: Decimal,
    quantity: Decimal,
    direction: str,
) -> Decimal:
    """Compute realized P&L when closing a position.

    Formula: (close_price - avg_cost) * quantity * sign
      sign = +1 for long, -1 for short.

    Returns a Decimal. Pure arithmetic — never touches the DB.
    """
    sign = Decimal("-1") if direction == "short" else Decimal("1")
    return (close_price - avg_cost) * quantity * sign
