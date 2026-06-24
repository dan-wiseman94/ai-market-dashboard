"""Shared forward-return helpers for the market app.

These functions compute price metrics over OHLC bars and are intended to be
reused by analytics, post-mortem, and any other consumers that need price
path data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.conf import settings
from django.db.models import Count, Max, Min

from apps.market.models import OHLCBar


def _pct_change(start_close: float | None, end_close: float | None) -> float | None:
    """Percent change from *start_close* to *end_close*, ``None`` on a missing or zero base."""
    if start_close is None or end_close is None or start_close == 0:
        return None
    return (end_close - start_close) / start_close * 100.0


def direction_verdict(direction: str, fwd_pct: float | None, *, deadzone: float = 1.0) -> str:
    """Deterministic ``correct|incorrect|mixed|inconclusive`` from a directional
    call and the actual forward return (percent). No AI involved.

    Shared by trader thesis post-mortems (``apps.thesis``) and AI predictions
    (``apps.predictions``) so both score a directional call the same way.
    ``direction`` is ``bullish|bearish|neutral``; ``deadzone`` is the symmetric
    flat band around 0% within which a directional call is treated as neither
    clearly right nor clearly wrong. ``None`` forward return → ``inconclusive``.
    """
    if fwd_pct is None:
        return "inconclusive"
    if direction == "neutral":
        # A neutral call is "correct" when the move stayed inside the deadzone.
        return "correct" if abs(fwd_pct) <= deadzone else "incorrect"
    if direction == "bullish":
        if fwd_pct >= deadzone:
            return "correct"
        if fwd_pct <= -deadzone:
            return "incorrect"
        return "mixed"
    # bearish
    if fwd_pct <= -deadzone:
        return "correct"
    if fwd_pct >= deadzone:
        return "incorrect"
    return "mixed"


def _corporate_actions(ticker: str, start: datetime, end: datetime) -> list:
    """Stored splits + dividends with ``start.date() < ex_date <= end.date()`` (lazy import
    to keep the returns module free of a service-layer import cycle)."""
    from apps.market.services.corporate_actions import corporate_actions_for

    return corporate_actions_for(ticker, start, end)


def _split_product(actions: list, *, on_or_before: date | None = None) -> float:
    """Product of split ratios (``shares_after/shares_before``) over *actions*.

    ``1.0`` when there are no qualifying splits. With ``on_or_before`` set, only
    splits whose ``ex_date`` is on or before that date count — used to scale a
    dividend onto the start-share basis by the splits that precede its ex-date.
    """
    factor = 1.0
    for a in actions:
        if (
            a.kind == "split"
            and a.ratio is not None
            and (on_or_before is None or a.ex_date <= on_or_before)
        ):
            factor *= float(a.ratio)
    return factor


def split_factor(ticker: str, after: datetime, until: datetime) -> float:
    """Product of split ratios (``shares_after/shares_before``) for ex-dates in
    ``(after, until]``. ``1.0`` when there are no splits — the common path, leaving
    returns identical to the pre-adjustment behaviour.

    Multiplying an ``until``-basis close by this factor restores it to the
    ``after``-basis, so a 3:1 split (ratio 3) no longer reads as a -66% crash.
    """
    return _split_product(_corporate_actions(ticker, after, until))


def _adjusted_end_value(
    ticker: str, start: datetime, end: datetime, end_close: float | None
) -> tuple[float | None, float]:
    """``(adjusted_end_value, split_factor)`` for ``end_close`` on the start-share basis.

    Splits are always applied (a split is a non-event for the holder). Dividends
    are added back — converting price-return to total-return — only when
    ``RETURNS_ADJUST_DIVIDENDS`` is on; each is scaled onto the start-share basis
    by the split ratios that precede its ex-date.
    """
    actions = _corporate_actions(ticker, start, end)
    factor = _split_product(actions)
    if end_close is None:
        return None, factor
    value = end_close * factor
    if getattr(settings, "RETURNS_ADJUST_DIVIDENDS", False):
        for a in actions:
            if a.kind != "dividend" or a.amount is None:
                continue
            value += float(a.amount) * _split_product(actions, on_or_before=a.ex_date)
    return value, factor


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
    """Percent change in *ticker*'s close price from *start* to *end*, corrected
    for corporate actions in the window.

    Uses :func:`nearest_bar_close` at each endpoint. A stock split between *start*
    and *end* would otherwise read as a crash (the end close is on a divided-price
    basis); the end close is restored to the start basis via :func:`_adjusted_end_value`.
    Returns ``None`` if either endpoint has no bar or if the start close is zero.
    """
    start_close = nearest_bar_close(ticker, start)
    adjusted_end, _factor = _adjusted_end_value(ticker, start, end, nearest_bar_close(ticker, end))
    return _pct_change(start_close, adjusted_end)


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

    Corporate-action note: the price fields (``start_close``, ``end_close``,
    ``max_high``, ``min_low``) are the **raw observed** values — facts as
    captured. Only ``return_pct`` is corrected for splits (and opt-in dividends).
    ``split_factor`` (Π split ratios in the window; ``1.0`` if none) and
    ``adjusted`` make a split visible, so a consumer seeing ``start_close=300``,
    ``end_close=100``, ``return_pct≈0``, ``split_factor=3`` can read it correctly.
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
    adjusted_end, factor = _adjusted_end_value(ticker, start, end, end_close)

    return {
        "start_close": start_close,
        "end_close": end_close,
        "return_pct": _pct_change(start_close, adjusted_end),
        "max_high": max_high,
        "min_low": min_low,
        "bars": agg["bars"],
        "split_factor": factor,
        "adjusted": factor != 1.0,
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
    adjusted_t1, _factor = _adjusted_end_value(ticker, at, target_close, t1)
    return _pct_change(t0, adjusted_t1)


def _nearest_close_within_inmem(
    bars: list[tuple[datetime, float]], at: datetime, *, tolerance_hours: float
) -> float | None:
    """In-memory twin of :func:`nearest_bar_close_within` over a ts-ascending
    ``(ts, close)`` list: the close of the most-recent bar with ts in
    ``[at - tolerance, at]``, or ``None``."""
    lo = at - timedelta(hours=tolerance_hours)
    best: float | None = None
    for ts, close in bars:  # ascending; keep the highest ts within [lo, at]
        if ts > at:
            break
        if ts >= lo:
            best = close
    return best


def _adjust_end_value_inmem(
    actions: list, start: datetime, end: datetime, end_close: float | None
) -> float | None:
    """In-memory twin of :func:`_adjusted_end_value` (returns just the adjusted value).

    ``actions`` is the ticker's full corporate-action list; only ex-dates in
    ``(start.date(), end.date()]`` are applied — the same window as
    :func:`apps.market.services.corporate_actions.corporate_actions_for`.
    """
    if end_close is None:
        return None
    window = [a for a in actions if start.date() < a.ex_date <= end.date()]
    factor = _split_product(window)
    value = end_close * factor
    if getattr(settings, "RETURNS_ADJUST_DIVIDENDS", False):
        for a in window:
            if a.kind != "dividend" or a.amount is None:
                continue
            value += float(a.amount) * _split_product(window, on_or_before=a.ex_date)
    return value


def trading_day_forward_returns(
    requests: list[tuple[str, datetime]], forward_hours: int
) -> list[float | None]:
    """Batched twin of :func:`trading_day_forward_return_pct` over many ``(ticker, at)``
    requests — O(1) DB queries instead of O(n).

    Pre-loads the OHLC bars + corporate actions for the distinct tickers in two queries,
    then computes every forward return in memory. The per-request math is identical to
    :func:`trading_day_forward_return_pct` (a differential test pins the equivalence), so
    callers get the same numbers, only without the per-row query fan-out. Results align
    with ``requests`` order; ``None`` is an honest coverage gap. Does NOT trigger the
    cold-ticker corporate-action backfill (this is the read-heavy analytics path).
    """
    from apps.market.calendar import add_trading_days, calendar_for, session_close_on
    from apps.market.models import CorporateAction

    if not requests:
        return []

    tickers = {t for t, _ in requests}
    sessions = max(1, round(forward_hours / 24))
    ats = [at for _, at in requests]
    # Generous bounds: a superset of every endpoint's ±12h window. Extra bars in memory
    # are harmless (the tolerance filter rejects them); a too-narrow window is not.
    lo = min(ats) - timedelta(days=7)
    hi = max(ats) + timedelta(days=sessions + 14)

    bars_by_ticker: dict[str, list[tuple[datetime, float]]] = {}
    for tk, ts, close in (
        OHLCBar.objects.filter(ticker__in=tickers, ts__gte=lo, ts__lte=hi)
        .order_by("ticker", "ts")
        .values_list("ticker", "ts", "close")
    ):
        bars_by_ticker.setdefault(tk, []).append((ts, float(close)))

    actions_by_ticker: dict[str, list] = {}
    for a in CorporateAction.objects.filter(ticker__in=tickers).order_by("ex_date"):
        actions_by_ticker.setdefault(a.ticker, []).append(a)

    out: list[float | None] = []
    for ticker, at in requests:
        market = calendar_for(ticker)
        target_day = add_trading_days(market, at, sessions)
        target_close = session_close_on(market, target_day.date()) or target_day
        bars = bars_by_ticker.get(ticker, [])
        t0 = _nearest_close_within_inmem(bars, at, tolerance_hours=12)
        t1 = _nearest_close_within_inmem(bars, target_close, tolerance_hours=12)
        adjusted_t1 = _adjust_end_value_inmem(
            actions_by_ticker.get(ticker, []), at, target_close, t1
        )
        out.append(_pct_change(t0, adjusted_t1))
    return out
