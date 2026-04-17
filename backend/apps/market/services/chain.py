"""Option chain fetching, normalization, and caching."""
from __future__ import annotations


def _fmt(x) -> str | None:
    if x is None:
        return None
    return f"{float(x):.2f}"


def _normalize_contract(c: dict) -> dict:
    return {
        "strike": _fmt(c.get("strikePrice")),
        "bid": _fmt(c.get("bid")),
        "ask": _fmt(c.get("ask")),
        "last": _fmt(c.get("last")),
        "volume": c.get("totalVolume"),
        "oi": c.get("openInterest"),
        "delta": _fmt(c.get("delta")),
        "gamma": _fmt(c.get("gamma")),
        "theta": _fmt(c.get("theta")),
        "vega": _fmt(c.get("vega")),
        "iv": _fmt(c.get("volatility")),
    }


def _flatten_side(exp_date_map: dict) -> dict[str, list[dict]]:
    """Flatten Schwab's nested {"YYYY-MM-DD:DTE": {"strike": [contract]}} → {"YYYY-MM-DD": [contracts...]}."""
    out: dict[str, list[dict]] = {}
    for key, strikes in (exp_date_map or {}).items():
        expiry = key.split(":", 1)[0]  # drop ":DTE" suffix
        contracts = []
        for _strike, listing in strikes.items():
            for c in listing:
                contracts.append(_normalize_contract(c))
        contracts.sort(key=lambda c: float(c["strike"] or 0))
        out[expiry] = contracts
    return out


def _normalize_chain(raw: dict) -> dict:
    """Schwab response → flat OptionChainSnapshot.payload shape."""
    calls_by_exp = _flatten_side(raw.get("callExpDateMap", {}))
    puts_by_exp = _flatten_side(raw.get("putExpDateMap", {}))
    expiries: dict[str, dict] = {}
    for exp in sorted(set(calls_by_exp) | set(puts_by_exp)):
        expiries[exp] = {
            "calls": calls_by_exp.get(exp, []),
            "puts": puts_by_exp.get(exp, []),
        }
    return {
        "underlying_last": _fmt(raw.get("underlyingPrice")),
        "expiries": expiries,
    }
