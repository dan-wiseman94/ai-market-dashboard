"""Shared forward-return helpers for the market app.

These functions compute price metrics over OHLC bars and are intended to be
reused by analytics, post-mortem, and any other consumers that need price
path data.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Count, Max, Min

from apps.market.models import OHLCBar


def nearest_bar_close(ticker: str, at: datetime) -> float | None:
    """Return the close of the most-recent bar for *ticker* at or before ``at + 1h``.

    Mirrors the leaderboard's original ``_nearest_bar_close`` logic verbatim.
    Filters by ticker only (not timeframe) to match existing behaviour.
    """
    bar = (
        OHLCBar.objects.filter(ticker=ticker, ts__lte=at + timedelta(hours=1))
        .only("close")
        .order_by("-ts")
        .first()
    )
    if bar is None:
        return None
    return float(bar.close)


def forward_return_pct(ticker: str, start: datetime, end: datetime) -> float | None:
    """Percent change in *ticker*'s close price from *start* to *end*.

    Uses :func:`nearest_bar_close` at each endpoint. Returns ``None`` if
    either endpoint has no bar or if the start close is zero (division guard).
    """
    t0 = nearest_bar_close(ticker, start)
    t1 = nearest_bar_close(ticker, end)
    if t0 is None or t1 is None or t0 == 0:
        return None
    return (t1 - t0) / t0 * 100.0


def price_path_summary(ticker: str, start: datetime, end: datetime) -> dict:
    """Aggregate price-action summary for *ticker* over [*start*, *end*].

    Returns a dict with:
    - ``start_close`` / ``end_close``: closes at the two endpoints (float | None)
    - ``return_pct``: forward return over the window (float | None)
    - ``max_high``: highest high across bars in range (float | None)
    - ``min_low``: lowest low across bars in range (float | None)
    - ``bars``: count of bars whose ``ts`` falls in [start, end] (int)

    The endpoint closes use :func:`nearest_bar_close` (same ±1h window logic).
    The aggregate stats cover only bars with ``ts`` in [start, end] exactly.

    Range-semantics note: ``end_close`` may reflect a bar with ts up to
    ``end + 1h`` (nearest_bar_close grace window), while ``max_high``,
    ``min_low``, and ``bars`` count only bars with ts in [start, end].
    A bar that falls in ``(end, end + 1h]`` therefore influences ``end_close``
    but is NOT counted in ``bars`` and does NOT affect ``max_high``/``min_low``.
    """
    agg = OHLCBar.objects.filter(
        ticker=ticker,
        ts__gte=start,
        ts__lte=end,
    ).aggregate(
        max_high=Max("high"),
        min_low=Min("low"),
        bars=Count("id"),
    )

    max_high = float(agg["max_high"]) if agg["max_high"] is not None else None
    min_low = float(agg["min_low"]) if agg["min_low"] is not None else None

    start_close = nearest_bar_close(ticker, start)
    end_close = nearest_bar_close(ticker, end)

    if start_close is None or end_close is None or start_close == 0:
        return_pct = None
    else:
        return_pct = (end_close - start_close) / start_close * 100.0

    return {
        "start_close": start_close,
        "end_close": end_close,
        "return_pct": return_pct,
        "max_high": max_high,
        "min_low": min_low,
        "bars": agg["bars"],
    }


def nearest_bar_close_within(ticker: str, at: datetime, *, tolerance_hours: float) -> float | None:
    """Most-recent bar close at/just before ``at``, only within ``tolerance_hours``.

    Unlike :func:`nearest_bar_close` (which looks back unbounded), this returns
    ``None`` when no real bar exists near ``at`` — so callers report an honest
    coverage gap instead of a stale fill.
    """
    lo = at - timedelta(hours=tolerance_hours)
    bar = (
        OHLCBar.objects.filter(ticker=ticker, ts__lte=at, ts__gte=lo)
        .only("close")
        .order_by("-ts")
        .first()
    )
    if bar is None:
        return None
    return float(bar.close)


def trading_day_forward_return_pct(ticker: str, at: datetime, forward_hours: int) -> float | None:
    """% change of ``ticker`` from ``at`` to +N trading sessions on its calendar.

    ``forward_hours`` is reinterpreted as trading sessions (24h -> 1 session).
    Returns ``None`` (coverage gap) when a real bar is missing within 12h of
    either endpoint — never a stale fill.
    """
    from apps.market.calendar import add_trading_days, calendar_for, session_close_on

    market = calendar_for(ticker)
    sessions = max(1, round(forward_hours / 24))
    target_day = add_trading_days(market, at, sessions)
    target_close = session_close_on(market, target_day.date()) or target_day
    t0 = nearest_bar_close_within(ticker, at, tolerance_hours=12)
    t1 = nearest_bar_close_within(ticker, target_close, tolerance_hours=12)
    if t0 is None or t1 is None or t0 == 0:
        return None
    return (t1 - t0) / t0 * 100.0
