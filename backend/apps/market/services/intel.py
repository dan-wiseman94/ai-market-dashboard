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


FACTOR_SPREADS: tuple[tuple[str, str, str], ...] = (
    ("momentum_minus_value", "MTUM", "VLUE"),
    ("small_minus_large", "IWM", "SPY"),
    ("growth_minus_value_proxy", "QQQ", "SPY"),
)


def factor_returns(etfs: list[str], *, windows: tuple[int, ...] = (1, 5, 20)) -> dict | None:
    """Per-ETF returns over each window plus long-short style spreads.

    Stored 1d bars only; an ETF with thin bars gets None per window, a spread
    with a missing leg is None, and the whole result is None when nothing has
    a value (honest coverage, same contract as sector_rotation)."""
    etf_rows: dict[str, dict[int, float | None]] = {}
    any_value = False
    for etf in etfs:
        row = {w: return_over_sessions(etf, w) for w in windows}
        any_value = any_value or any(v is not None for v in row.values())
        etf_rows[etf.upper()] = row
    if not any_value:
        return None
    spreads: dict[str, dict[int, float | None]] = {}
    for name, long_leg, short_leg in FACTOR_SPREADS:
        spreads[name] = {}
        for w in windows:
            lo = return_over_sessions(long_leg, w)
            sh = return_over_sessions(short_leg, w)
            spreads[name][w] = round(lo - sh, 4) if lo is not None and sh is not None else None
    return {"windows": list(windows), "etfs": etf_rows, "spreads": spreads}


def _closes(ticker: str, limit: int) -> list[float]:
    return [
        float(b.close)
        for b in OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d").order_by("-ts")[
            :limit
        ]
    ]


def breadth_stats(
    tickers: list[str],
    *,
    sma_periods: tuple[int, ...] = (20, 50),
    hl_window: int = 252,
) -> dict | None:
    """% of tickers above their N-session SMA + fresh high/low counts.

    The high/low span clamps to the bars actually stored (retention prunes at
    ~400 calendar days); min_span_sessions reports the smallest span used so
    the render can label the REAL window. None when < 3 tickers usable."""
    sma: dict[int, dict] = {}
    for period in sma_periods:
        above = total = 0
        for t in tickers:
            closes = _closes(t, period)
            if len(closes) < period:
                continue
            total += 1
            if closes[0] > sum(closes) / len(closes):
                above += 1
        sma[period] = {
            "above": above,
            "n": total,
            "pct": round(above / total * 100, 1) if total else None,
        }
    highs = lows = counted = 0
    min_span: int | None = None
    for t in tickers:
        closes = _closes(t, hl_window)
        if len(closes) < 20:
            continue
        counted += 1
        min_span = len(closes) if min_span is None else min(min_span, len(closes))
        last, rest = closes[0], closes[1:]
        if rest and last >= max(rest):
            highs += 1
        if rest and last <= min(rest):
            lows += 1
    if counted < 3:
        return None
    return {
        "pct_above_sma": sma,
        "highs": highs,
        "lows": lows,
        "hl_n": counted,
        "hl_window": hl_window,
        "min_span_sessions": min_span,
    }
