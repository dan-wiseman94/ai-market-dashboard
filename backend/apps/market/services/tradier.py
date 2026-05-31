"""Option chain fetching via Tradier sandbox API (15-min delayed, free tier).

Sourced from Tradier (https://sandbox.tradier.com/v1):
- GET /markets/options/expirations  → expiry date list
- GET /markets/options/chains       → per-expiry option contracts with greeks
- GET /markets/quotes               → underlying last price

Cached per cache.ttl_for_kind("chain"). Persists OptionChainSnapshot on each
real fetch. Never raises — returns {"ticker": ..., "underlying_last": None, "expiries": {}}
on any failure.
"""

from __future__ import annotations

import logging

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

TRADIER_BASE = "https://sandbox.tradier.com/v1"


def _api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="tradier")
    except ApiCredential.DoesNotExist:
        return None
    return (cred.token or {}).get("api_key")


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _get(path: str, params: dict, *, api_key: str) -> dict:
    resp = requests.get(
        f"{TRADIER_BASE}{path}",
        params=params,
        headers=_headers(api_key),
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def _fmt(x) -> str | None:
    """Format a numeric value as a 2-decimal-place string, or None."""
    if x is None:
        return None
    try:
        return f"{float(x):.2f}"
    except (ValueError, TypeError):
        return None


def _normalize_contract(opt: dict) -> dict:
    """Normalize a single Tradier option contract to the chain contract shape."""
    greeks = opt.get("greeks") or {}
    iv_raw = greeks.get("mid_iv") if greeks else None
    if iv_raw is None and greeks:
        iv_raw = greeks.get("smv_vol")

    return {
        "strike": _fmt(opt.get("strike")),
        "bid": _fmt(opt.get("bid")),
        "ask": _fmt(opt.get("ask")),
        "last": _fmt(opt.get("last")),
        "volume": opt.get("volume"),
        "oi": opt.get("open_interest"),
        "delta": _fmt(greeks.get("delta")) if greeks else None,
        "gamma": _fmt(greeks.get("gamma")) if greeks else None,
        "theta": _fmt(greeks.get("theta")) if greeks else None,
        "vega": _fmt(greeks.get("vega")) if greeks else None,
        "iv": _fmt(iv_raw),
    }


def _normalize_expirations(body: dict) -> list[str]:
    """Extract a flat list of expiry date strings from the expirations response."""
    dates = (body.get("expirations") or {}).get("date") or []
    if isinstance(dates, str):
        dates = [dates]
    return list(dates)


def _normalize_chain_options(body: dict) -> tuple[list[dict], list[dict]]:
    """Split options from a chain response into (calls, puts), each normalized."""
    options_wrapper = body.get("options") or {}
    option_list = options_wrapper.get("option") or []
    if isinstance(option_list, dict):
        option_list = [option_list]

    calls: list[dict] = []
    puts: list[dict] = []
    for opt in option_list:
        contract = _normalize_contract(opt)
        if opt.get("option_type") == "call":
            calls.append(contract)
        elif opt.get("option_type") == "put":
            puts.append(contract)

    calls.sort(key=lambda c: float(c["strike"] or 0))
    puts.sort(key=lambda c: float(c["strike"] or 0))
    return calls, puts


def _normalize_quote(body: dict, ticker: str) -> str | None:
    """Extract the last price from a quotes response, formatted as 2dp string."""
    quote_val = (body.get("quotes") or {}).get("quote") or {}
    if isinstance(quote_val, list):
        # Multiple quotes returned — find the matching one or take the first
        matched = next((q for q in quote_val if q.get("symbol") == ticker.upper()), None)
        quote_val = matched or (quote_val[0] if quote_val else {})
    return _fmt(quote_val.get("last"))


def _canned_chain(ticker: str) -> dict:
    """Deterministic canned chain for MOCK_EXTERNAL / e2e mode."""
    return {
        "ticker": ticker,
        "underlying_last": "150.00",
        "expiries": {
            "2026-01-16": {
                "calls": [
                    {
                        "strike": "145.00",
                        "bid": "6.20",
                        "ask": "6.40",
                        "last": "6.30",
                        "volume": 500,
                        "oi": 2000,
                        "delta": "0.65",
                        "gamma": "0.04",
                        "theta": "-0.05",
                        "vega": "0.12",
                        "iv": "0.28",
                    }
                ],
                "puts": [
                    {
                        "strike": "145.00",
                        "bid": "1.10",
                        "ask": "1.20",
                        "last": "1.15",
                        "volume": 300,
                        "oi": 1500,
                        "delta": "-0.35",
                        "gamma": "0.04",
                        "theta": "-0.05",
                        "vega": "0.12",
                        "iv": "0.28",
                    }
                ],
            }
        },
    }


def fetch_chain(ticker: str, *, max_expiries: int = 2) -> dict:
    """Fetch, cache, and persist an option chain for ``ticker`` via Tradier sandbox.

    Returns the chain contract dict. On any failure returns
    ``{"ticker": ticker, "underlying_last": None, "expiries": {}}``.
    Never raises.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()
    empty: dict = {"ticker": ticker, "underlying_last": None, "expiries": {}}

    if is_mock_mode():
        return _canned_chain(ticker)

    api_key = _api_key()
    if not api_key:
        log.info("market.tradier: no credential configured, skipping fetch")
        return empty

    try:
        # 1. Fetch expiration dates
        exp_body = cache.get_or_fetch(
            f"market:tradier:expirations:{ticker}",
            ttl_seconds=cache.ttl_for_kind("chain"),
            fetcher=lambda: _get(
                "/markets/options/expirations",
                {"symbol": ticker, "includeAllRoots": "true"},
                api_key=api_key,
            ),
        )
        expiry_dates = _normalize_expirations(exp_body)[:max_expiries]

        if not expiry_dates:
            log.info("market.tradier: no expirations found for %s", ticker)
            return empty

        # 2. Fetch underlying last price
        quote_body = cache.get_or_fetch(
            f"market:tradier:quote:{ticker}",
            ttl_seconds=cache.ttl_for_kind("chain"),
            fetcher=lambda: _get(
                "/markets/quotes",
                {"symbols": ticker},
                api_key=api_key,
            ),
        )
        underlying_last = _normalize_quote(quote_body, ticker)

        # 3. Fetch chain per expiry
        expiries: dict[str, dict] = {}
        for expiry in expiry_dates:
            chain_body = cache.get_or_fetch(
                f"market:tradier:chain:{ticker}:{expiry}",
                ttl_seconds=cache.ttl_for_kind("chain"),
                fetcher=lambda exp=expiry: _get(
                    "/markets/options/chains",
                    {"symbol": ticker, "expiration": exp, "greeks": "true"},
                    api_key=api_key,
                ),
            )
            calls, puts = _normalize_chain_options(chain_body)
            expiries[expiry] = {"calls": calls, "puts": puts}

        payload: dict = {
            "ticker": ticker,
            "underlying_last": underlying_last,
            "expiries": expiries,
        }

        # Persist snapshot (best-effort — don't let a DB error surface to caller)
        try:
            from apps.market.models import OptionChainSnapshot

            OptionChainSnapshot.objects.create(
                ticker=ticker,
                expiries=list(payload["expiries"].keys()),
                payload=payload,
            )
        except Exception as exc:
            log.warning("market.tradier.persist_failed %s: %s", ticker, exc)

        return payload

    except Exception as exc:
        log.warning("market.tradier.fetch_failed %s: %s", ticker, exc)
        return empty
