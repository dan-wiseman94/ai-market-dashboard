"""US Treasury fiscal data: average interest rates + total public debt.

Sourced from the FiscalData API (api.fiscaldata.treasury.gov) — no API key required.
- GET /v2/accounting/od/avg_interest_rates   → latest average interest rates by security
- GET /v2/accounting/od/debt_to_penny        → total public debt outstanding

Both calls are cached 6 hours (TTL key "treasury").  Each sub-fetch is independent —
one failure never kills the other.  Never raises; returns {} on any failure.

Note: the daily par yield curve from Treasury is XML-only; DGS* yield-curve series are
sourced via FRED (fred.py).  This module covers the FiscalData JSON endpoints only.
"""

from __future__ import annotations

import logging

import requests  # type: ignore[import-untyped]

from apps.market import cache

log = logging.getLogger(__name__)

FISCALDATA_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


def _get(path: str, params: dict) -> dict:
    resp = requests.get(f"{FISCALDATA_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Canned fixtures for MOCK_EXTERNAL / e2e mode
# ---------------------------------------------------------------------------


def _canned_rates() -> dict:
    """Deterministic fixture for average interest rates."""
    return {
        "record_date": "2025-04-30",
        "rates": {
            "Treasury Bills": 4.32,
            "Treasury Notes": 4.15,
            "Treasury Bonds": 4.55,
            "Treasury Inflation-Protected Securities (TIPS)": 1.87,
            "Federal Financing Bank": 4.80,
        },
    }


def _canned_debt() -> dict:
    """Deterministic fixture for debt-to-penny."""
    return {
        "record_date": "2025-05-29",
        "total_public_debt": 36_200_000_000_000.0,
    }


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------


def _normalize_rates(body: dict) -> dict:
    """Extract rates for the latest record_date from a raw avg_interest_rates response."""
    rows = body.get("data") or []
    if not rows:
        return {}

    # Find the latest record_date across all returned rows
    latest_date = ""
    for row in rows:
        rd = row.get("record_date") or ""
        if rd > latest_date:
            latest_date = rd

    if not latest_date:
        return {}

    rates: dict[str, float] = {}
    for row in rows:
        if row.get("record_date") != latest_date:
            continue
        desc = row.get("security_desc") or row.get("security_type_desc") or ""
        raw_rate = row.get("avg_interest_rate_amt")
        if not desc or raw_rate is None:
            continue
        try:
            rates[desc] = float(raw_rate)
        except (ValueError, TypeError):
            log.warning("treasury.rates.skip_row desc=%r raw=%r", desc, raw_rate)

    return {"record_date": latest_date, "rates": rates}


def _normalize_debt(body: dict) -> dict:
    """Extract debt-to-penny from a raw debt_to_penny response."""
    rows = body.get("data") or []
    if not rows:
        return {}
    row = rows[0]
    record_date = row.get("record_date") or ""
    raw_debt = row.get("tot_pub_debt_out_amt")
    if raw_debt is None:
        return {}
    try:
        total = float(raw_debt)
    except (ValueError, TypeError):
        log.warning("treasury.debt.parse_failed raw=%r", raw_debt)
        return {}
    return {"record_date": record_date, "total_public_debt": total}


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------


def fetch_treasury_rates() -> dict:
    """Cached 6h average interest rates by security description.

    Returns {"record_date": "YYYY-MM-DD", "rates": {security_desc: float}}.
    Returns {} on missing data or fetch failure (never raises).
    In mock mode returns a deterministic canned dict.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _canned_rates()

    try:
        body = cache.get_or_fetch(
            "market:treasury:rates",
            ttl_seconds=cache.ttl_for_kind("treasury"),
            fetcher=lambda: _get(
                "/v2/accounting/od/avg_interest_rates",
                {
                    "sort": "-record_date",
                    "page[size]": 50,
                    "fields": "record_date,security_type_desc,security_desc,avg_interest_rate_amt",
                },
            ),
        )
    except Exception as exc:
        log.warning("market.treasury.fetch_rates_failed: %s", exc)
        return {}

    return _normalize_rates(body)


def fetch_debt_to_penny() -> dict:
    """Cached 6h total public debt outstanding.

    Returns {"record_date": "YYYY-MM-DD", "total_public_debt": float}.
    Returns {} on missing data or fetch failure (never raises).
    In mock mode returns a deterministic canned dict.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _canned_debt()

    try:
        body = cache.get_or_fetch(
            "market:treasury:debt",
            ttl_seconds=cache.ttl_for_kind("treasury"),
            fetcher=lambda: _get(
                "/v2/accounting/od/debt_to_penny",
                {
                    "sort": "-record_date",
                    "page[size]": 1,
                    "fields": "record_date,tot_pub_debt_out_amt",
                },
            ),
        )
    except Exception as exc:
        log.warning("market.treasury.fetch_debt_failed: %s", exc)
        return {}

    return _normalize_debt(body)


def fetch_treasury() -> dict:
    """Combined Treasury section payload: average interest rates + total debt.

    Returns {"rates": {...}, "debt": {...}}.  Each sub-fetch is independent —
    one failure does not suppress the other.  Never raises.
    """
    return {
        "rates": fetch_treasury_rates(),
        "debt": fetch_debt_to_penny(),
    }
