"""Option chain fetching, normalization, and caching."""

from __future__ import annotations

import hashlib
import json

from apps.market import cache
from apps.market.models import OptionChainSnapshot
from apps.market.schwab_client import (
    SchwabNotConnectedError,
    get_schwab_client,
    schwab_json,
)
from apps.market.symbols import normalize_symbol


def _fmt(x) -> str | None:
    if x is None:
        return None
    try:
        return f"{float(x):.2f}"
    except (ValueError, TypeError):
        return None


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
    """Flatten Schwab's nested {"YYYY-MM-DD:DTE": {"strike": [contract]}} -> {"YYYY-MM-DD": [contracts...]}."""
    out: dict[str, list[dict]] = {}
    for key, strikes in (exp_date_map or {}).items():
        expiry = key.split(":", 1)[0]
        bucket = out.setdefault(expiry, [])
        for listing in strikes.values():
            bucket.extend(_normalize_contract(c) for c in listing)
    for contracts in out.values():
        contracts.sort(key=lambda c: float(c["strike"] or 0))
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


def fetch_chain(
    ticker: str,
    *,
    strikes_around_atm: int = 10,
) -> dict:
    """Fetch + cache + persist an option chain for `ticker`.

    On cache miss: call Schwab, normalize, persist OptionChainSnapshot, return payload.
    On cache hit: return cached payload (no DB write).
    """
    ticker = normalize_symbol(ticker)
    # Short cache-key fingerprint (not a security digest) — sha256 truncated.
    params_hash = hashlib.sha256(
        json.dumps({"k": strikes_around_atm}, sort_keys=True).encode(),
    ).hexdigest()[:8]
    cache_key = f"market:chain:{ticker}:{params_hash}"

    def _fetch_and_persist() -> dict:
        client = get_schwab_client()
        resp = client.get_option_chain(
            symbol=ticker,
            contract_type=client.Options.ContractType.ALL,
            strike_count=strikes_around_atm * 2,
            include_underlying_quote=True,
        )
        payload = _normalize_chain(schwab_json(resp))
        payload["ticker"] = ticker
        OptionChainSnapshot.objects.create(
            ticker=ticker,
            expiries=list(payload["expiries"].keys()),
            payload=payload,
        )
        return payload

    try:
        return cache.get_or_fetch(
            cache_key,
            ttl_seconds=cache.ttl_for_kind("chain"),
            fetcher=_fetch_and_persist,
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_chain(ticker)
        if alt is None:
            raise
        return alt
