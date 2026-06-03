"""Dollar Value-at-Risk + factor-beta-to-$SPX lens over the union book.

Parametric (Gaussian) 1-day 95% VaR off stored daily returns — the natural
next depth on top of the conviction-weighted units + correlation clusters.
Only positions that carry a dollar size *and* enough price history are priced;
everything else (coverage/thesis-only names) is reported as skipped rather than
silently dropped. Reuses the same OHLCBar return series the clusters use."""

from __future__ import annotations

import statistics

from apps.book import constants as C
from apps.book.services.correlation import _daily_returns

SPX_SYMBOL = "$SPX"
_METHOD = "parametric_gaussian_1d_95"


def _beta(asset: list[float], market: list[float]) -> float | None:
    """cov(asset, market) / var(market) over the overlapping tail. None when the
    overlap is too short or the market has no variance."""
    n = min(len(asset), len(market))
    if n < C.VAR_MIN_BARS:
        return None
    a, m = asset[-n:], market[-n:]
    mean_m = sum(m) / n
    var_m = sum((x - mean_m) ** 2 for x in m)
    if var_m <= 0:
        return None
    mean_a = sum(a) / n
    cov = sum((a[i] - mean_a) * (m[i] - mean_m) for i in range(n))
    return cov / var_m


def _unavailable(window: int, note: str) -> dict:
    return {
        "available": False,
        "method": _METHOD,
        "window": window,
        "positions": [],
        "portfolio": {},
        "note": note,
    }


def compute_var_beta(exposures: list[dict]) -> dict:
    window = C.VAR_WINDOW
    spx = _daily_returns(SPX_SYMBOL, window)

    positions: list[dict] = []
    series: list[tuple[float, list[float]]] = []  # (signed_dollar, returns)
    skipped = 0
    for e in exposures:
        dollar = e.get("dollar")
        if dollar is None:
            skipped += 1  # coverage/thesis-only name — no dollar to put at risk
            continue
        rets = _daily_returns(e["ticker"], window)
        if len(rets) < C.VAR_MIN_BARS:
            skipped += 1
            continue
        dollar = float(dollar)
        sigma = statistics.pstdev(rets)
        beta = _beta(rets, spx) if spx else None
        positions.append(
            {
                "ticker": e["ticker"],
                "dollar": round(dollar, 2),
                "daily_vol_pct": round(sigma * 100, 3),
                "var_usd": round(C.VAR_Z_95 * sigma * abs(dollar), 2),
                "beta": round(beta, 3) if beta is not None else None,
            }
        )
        series.append((dollar, rets))

    if not positions:
        return _unavailable(window, "No dollar-sized positions with enough history to size risk.")

    # Portfolio P&L series in dollars, aligned by recency — its std embeds the
    # cross-position correlation, so diversified VaR <= sum of position VaRs.
    length = min(len(r) for _, r in series)
    aligned = [(dollar, r[-length:]) for dollar, r in series]
    pnl = [sum(dollar * r[t] for dollar, r in aligned) for t in range(length)]
    port_sigma = statistics.pstdev(pnl) if length >= 2 else 0.0
    diversified = C.VAR_Z_95 * port_sigma
    undiversified = sum(p["var_usd"] for p in positions)

    portfolio = {
        "gross_dollar": round(sum(abs(d) for d, _ in series), 2),
        "net_dollar": round(sum(d for d, _ in series), 2),
        "undiversified_var_usd": round(undiversified, 2),
        "diversified_var_usd": round(diversified, 2),
        "diversification_benefit_usd": round(undiversified - diversified, 2),
        # Net SPX-equivalent dollar exposure: how much $SPX the book moves like.
        "beta_adjusted_net_exposure_usd": round(
            sum(p["dollar"] * (p["beta"] or 0.0) for p in positions), 2
        ),
        "n_positions": len(positions),
    }
    return {
        "available": True,
        "method": _METHOD,
        "window": window,
        "positions": positions,
        "portfolio": portfolio,
        "skipped": skipped,
        "note": "" if spx else "$SPX history unavailable — betas omitted.",
    }
