"""VIX term structure: spot $VIX vs /VX futures (front + second month).

VX final settlement is anchored to SPX options, not the contract's own month:
30 days before the third Friday of the *following* month, and when that Friday
is an exchange holiday, 30 days before the preceding business day (Good Friday
periodically lands on a third Friday and turns the usual settlement Wednesday
into a Tuesday). The dated-contract symbols this module builds (``/VXU26``)
pass through ``normalize_symbol`` untouched.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from apps.market.calendar.registry import get_market_calendar
from apps.market.services.quotes import fetch_quotes

MONTH_CODES = "FGHJKMNQUVXZ"  # Jan..Dec futures month codes


def vx_contract_symbol(year: int, month: int) -> str:
    """Schwab symbol for the monthly VX contract, e.g. ``/VXU26``."""
    return f"/VX{MONTH_CODES[month - 1]}{year % 100:02d}"


def _third_friday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)


def _is_trading_day(day: dt.date) -> bool:
    cal = get_market_calendar("cfe_futures")
    return len(cal.valid_days(day, day)) == 1


def vx_settlement_date(year: int, month: int) -> dt.date:
    """Final settlement date for the VX contract of the given month.

    Cboe's rule has two holiday branches off the nominal Wednesday (30 days
    before the following month's third Friday): if the anchor Friday is a
    holiday (Good Friday, e.g. Mar 2025 -> Tue Mar 18) OR the Wednesday itself
    is one (Juneteenth, e.g. Jun 2024 -> Tue Jun 18), settlement moves to the
    business day immediately preceding that Wednesday.
    """
    anchor_year, anchor_month = (year + 1, 1) if month == 12 else (year, month + 1)
    anchor = _third_friday(anchor_year, anchor_month)
    settlement = anchor - dt.timedelta(days=30)
    if not _is_trading_day(anchor) or not _is_trading_day(settlement):
        settlement -= dt.timedelta(days=1)
        while not _is_trading_day(settlement):
            settlement -= dt.timedelta(days=1)
    return settlement


def front_and_second(today: dt.date) -> list[tuple[str, dt.date]]:
    """The two nearest live contracts as ``(symbol, settlement)`` pairs.

    A contract always settles mid-way through its own calendar month, so the
    walk starts at *today's* month. Strict ``>`` rolls on settlement day
    itself: the expiring contract prices off the morning SOQ and is no longer
    a usable front month.
    """
    out: list[tuple[str, dt.date]] = []
    year, month = today.year, today.month
    while len(out) < 2:
        settlement = vx_settlement_date(year, month)
        if settlement > today:
            out.append((vx_contract_symbol(year, month), settlement))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _leg(symbol: str, quote: dict, expiry: dt.date | None) -> dict:
    return {
        "symbol": symbol,
        "expiry": expiry.isoformat() if expiry else None,
        "last": quote.get("last"),
        "pct_change": quote.get("pct_change"),
    }


def _round(value: float | None) -> float | None:
    return round(value, 2) if isinstance(value, int | float) else None


def _usable(quote: dict | None) -> dict | None:
    """A quote row counts only with a positive numeric last.

    Fallback providers answer unknown symbols with all-None rows (Twelve Data
    normalizes per-symbol error objects) and feeds emit 0.0 placeholders —
    both would fabricate legs/basis if treated as data.
    """
    last = (quote or {}).get("last")
    return quote if isinstance(last, int | float) and last > 0 else None


def vix_term_structure(*, today: dt.date | None = None) -> dict:
    """Spot $VIX plus the front/second-month /VX legs, with basis + contango.

    One batched quote call; the continuous ``/VX`` rides along as a safety net
    so a mis-rolled dated symbol degrades to a front leg with no expiry rather
    than no futures at all. Missing futures legs degrade to ``None`` with an
    explanatory ``note`` (the free fallback providers cannot quote CFE
    futures); only a fully-empty quote response raises.
    """
    today = today or dt.datetime.now(ZoneInfo("America/New_York")).date()
    front_exp: dt.date | None
    (front_sym, front_exp), (second_sym, second_exp) = front_and_second(today)
    quotes = fetch_quotes(["$VIX", "/VX", front_sym, second_sym])

    spot_q = _usable(quotes.get("$VIX"))
    front_q, continuous = _usable(quotes.get(front_sym)), False
    if front_q is None and (cont := _usable(quotes.get("/VX"))) is not None:
        front_sym, front_exp, front_q, continuous = "/VX", None, cont, True
    second_q = _usable(quotes.get(second_sym))
    if spot_q is None and front_q is None and second_q is None:
        raise RuntimeError("no VIX spot or futures quotes returned")

    payload: dict = {
        "spot": (
            {"symbol": "$VIX", "last": spot_q.get("last"), "pct_change": spot_q.get("pct_change")}
            if spot_q is not None
            else None
        ),
        "front": None,
        "second": _leg(second_sym, second_q, second_exp) if second_q is not None else None,
        "contango_pct": None,
        "structure": None,
    }

    if front_q is not None:
        front = _leg(front_sym, front_q, front_exp)
        front["continuous"] = continuous
        spot_last = (spot_q or {}).get("last")
        front_last = front["last"]
        basis = (
            front_last - spot_last
            if isinstance(front_last, int | float) and isinstance(spot_last, int | float)
            else None
        )
        front["basis"] = _round(basis)
        front["basis_pct"] = _round(
            basis / spot_last * 100 if basis is not None and spot_last else None
        )
        payload["front"] = front

    front_last = (payload["front"] or {}).get("last")
    second_last = (payload["second"] or {}).get("last")
    if isinstance(front_last, int | float) and isinstance(second_last, int | float) and front_last:
        contango = (second_last - front_last) / front_last * 100
        payload["contango_pct"] = _round(contango)
        payload["structure"] = (
            "contango" if contango > 0 else "backwardation" if contango < 0 else "flat"
        )

    if payload["front"] is None:
        payload["note"] = "VIX futures unavailable (requires Schwab connection)"
    elif payload["second"] is None:
        payload["note"] = "second-month /VX unavailable; contango not computable"
    return payload
