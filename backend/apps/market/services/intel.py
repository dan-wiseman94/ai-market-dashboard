"""Relative-strength and sector-rotation helpers.

Read-only over stored OHLCBar rows (daily timeframe).  Never fetches from
external APIs — coverage degrades honestly to None / [] when bars are thin.
"""

from __future__ import annotations

from apps.market.models import OHLCBar

BENCHMARK = "$SPX"
RS_WINDOWS = (1, 5, 20)  # trading sessions


def return_over_sessions(ticker: str, sessions: int) -> float | None:
    """Pct change in daily close over the last ``sessions`` trading bars.

    Reads from OHLCBar (``timeframe="1d"``) in reverse-chronological order and
    requires at least ``sessions + 1`` bars so that both the current close and
    the prior-session close are available.  Returns None when data is thin.
    """
    bars = list(
        OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d").order_by("-ts")[
            : sessions + 1
        ]
    )
    if len(bars) < sessions + 1:
        return None
    latest = float(bars[0].close)
    prior = float(bars[sessions].close)
    if not prior:
        return None
    return round((latest - prior) / prior * 100, 4)


def relative_strength(
    ticker: str,
    *,
    benchmark: str = BENCHMARK,
    windows: tuple[int, ...] = RS_WINDOWS,
) -> dict | None:
    """Primary-ticker return minus benchmark return over each window.

    Returns None when *ticker* is falsy or has no usable bars at all.
    Per-window ``rs`` is None when either side lacks bars (honest coverage).
    """
    if not ticker:
        return None
    out: dict[int, dict] = {}
    any_value = False
    for w in windows:
        t = return_over_sessions(ticker, w)
        b = return_over_sessions(benchmark, w)
        rs = round(t - b, 4) if (t is not None and b is not None) else None
        out[w] = {"ticker_pct": t, "benchmark_pct": b, "rs": rs}
        any_value = any_value or (t is not None)
    if not any_value:
        return None
    return {"ticker": ticker.upper(), "benchmark": benchmark, "windows": out}


def sector_rotation(
    *,
    benchmark: str = BENCHMARK,
    window: int = 5,
    sectors: list[str] | None = None,
) -> list[dict]:
    """Each sector ETF's return over ``window`` sessions and its RS vs benchmark.

    Sorted RS-descending (leaders first).  Skips sectors with no bars.
    Returns [] when none have data (honest coverage).
    """
    from apps.market.services.context import SECTOR_ETFS

    etfs = sectors if sectors is not None else SECTOR_ETFS
    b = return_over_sessions(benchmark, window)
    rows: list[dict] = []
    for etf in etfs:
        r = return_over_sessions(etf, window)
        if r is None:
            continue
        rs = round(r - b, 4) if b is not None else None
        rows.append({"sector": etf, "return_pct": r, "rs": rs})
    rows.sort(
        key=lambda x: (x["rs"] is not None, x["rs"] if x["rs"] is not None else 0.0),
        reverse=True,
    )
    return rows
