"""Derived market intelligence: sector rotation, relative strength, IV summary.

Pure analytics composed from data the capture pipeline already fetches or
stores. Snapshot-agnostic; each public function returns a plain dict or None.
"""

from __future__ import annotations

from apps.market.services.context import SECTOR_ETFS
from apps.market.services.quotes import fetch_quotes

_SECTOR_NAMES = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Cons. Disc.",
    "XLP": "Cons. Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Comm. Svcs.",
}


def _to_float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def sector_rotation() -> dict | None:
    """Rank the 11 sector ETFs by today's % change (leaders → laggards)."""
    quotes = fetch_quotes(SECTOR_ETFS)
    ranked: list[dict] = []
    for etf in SECTOR_ETFS:
        pct = _to_float((quotes.get(etf) or {}).get("pct_change"))
        if pct is None:
            continue
        ranked.append({"etf": etf, "sector": _SECTOR_NAMES.get(etf, etf), "pct": round(pct, 2)})
    if not ranked:
        return None
    ranked.sort(key=lambda r: r["pct"], reverse=True)
    return {"ranked": ranked}


def _atm_iv(lines: list[dict], underlying: float | None, parse_iv) -> float | None:
    """IV of the contract whose strike is nearest `underlying`."""
    if underlying is None:
        return None
    best = None
    for line in lines or []:
        strike = _to_float(line.get("strike"))
        if strike is None:
            continue
        dist = abs(strike - underlying)
        if best is None or dist < best[0]:
            best = (dist, parse_iv(line.get("iv")))
    return best[1] if best else None


def iv_summary(ticker: str, *, at) -> dict | None:
    """ATM IV z-score + percentile (vs 30-day history) + skew + term structure.

    Returns None for a falsy ticker, no chain snapshot, or indeterminable ATM IV.
    """
    import statistics
    from datetime import timedelta

    from apps.analytics.services.unusual_options import iv_values, parse_iv
    from apps.market.models import OptionChainSnapshot

    if not ticker:
        return None
    ticker = ticker.upper()
    latest = (
        OptionChainSnapshot.objects.filter(ticker=ticker, fetched_at__lte=at)
        .order_by("-fetched_at")
        .first()
    )
    if latest is None:
        return None
    payload = latest.payload or {}
    expiries = payload.get("expiries") or {}
    if not expiries:
        return None
    underlying = _to_float(payload.get("underlying_last"))
    exps = sorted(expiries.keys())
    front = expiries[exps[0]]
    front_call = _atm_iv(front.get("calls"), underlying, parse_iv)
    front_put = _atm_iv(front.get("puts"), underlying, parse_iv)
    atm_iv = front_call if front_call is not None else front_put
    if atm_iv is None:
        return None

    result: dict = {"ticker": ticker, "atm_iv": round(atm_iv, 4)}

    history = list(
        OptionChainSnapshot.objects.filter(
            ticker=ticker,
            fetched_at__gte=at - timedelta(days=30),
            fetched_at__lt=latest.fetched_at,
        ).order_by("fetched_at")
    )
    ivs = iv_values(history)
    if len(ivs) >= 2:
        mean = statistics.mean(ivs)
        stdev = statistics.stdev(ivs)
        result["mean_30d"] = round(mean, 4)
        if stdev:
            result["z"] = round((atm_iv - mean) / stdev, 2)
        result["percentile"] = round(sum(1 for v in ivs if v <= atm_iv) / len(ivs), 2)

    if front_put is not None and front_call is not None:
        result["skew"] = round(front_put - front_call, 4)

    if len(exps) >= 2:
        nxt = expiries[exps[1]]
        next_iv = _atm_iv(nxt.get("calls"), underlying, parse_iv)
        if next_iv is None:
            next_iv = _atm_iv(nxt.get("puts"), underlying, parse_iv)
        if next_iv is not None:
            result["term"] = {
                "front": exps[0],
                "front_iv": round(atm_iv, 4),
                "next": exps[1],
                "next_iv": round(next_iv, 4),
                "shape": "backwardation" if atm_iv > next_iv else "contango",
            }
    return result
