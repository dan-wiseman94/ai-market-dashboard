"""Company fundamentals: P/E, EPS, margins, growth, market cap, 52wk, sector.

Sourced from Finnhub (free-tier endpoints):
- GET /stock/metric?symbol=<T>&metric=all   → metric dict
- GET /stock/profile2?symbol=<T>            → sector / industry

Cached 24h per ticker. Upserts CompanyFundamentals on each real fetch.
Never raises — returns {} on any failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="finnhub")
    except ApiCredential.DoesNotExist:
        return None
    return (cred.token or {}).get("api_key")


def _finnhub_get(path: str, params: dict, api_key: str) -> dict:
    p = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=p, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def _canned_fundamentals(ticker: str) -> dict:
    """Deterministic canned dict for MOCK_EXTERNAL/e2e mode."""
    return {
        "ticker": ticker,
        "pe": 28.5,
        "eps_ttm": 6.42,
        "gross_margin": 43.5,
        "net_margin": 25.3,
        "rev_growth_yoy": 8.1,
        "market_cap": 2_800_000.0,
        "beta": 1.23,
        "div_yield": 0.51,
        "wk52_high": 199.0,
        "wk52_low": 142.0,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def _normalize(ticker: str, metric_body: dict, profile_body: dict) -> dict:
    """Build the normalized fundamentals dict from raw Finnhub responses."""
    m = metric_body.get("metric") or {}
    return {
        "ticker": ticker,
        "pe": m.get("peTTM"),
        "eps_ttm": m.get("epsBasicExclExtraTTM") or m.get("epsTTM"),
        "gross_margin": m.get("grossMarginTTM"),
        "net_margin": m.get("netProfitMarginTTM"),
        "rev_growth_yoy": m.get("revenueGrowthTTMYoy"),
        "market_cap": m.get("marketCapitalization"),
        "beta": m.get("beta"),
        "div_yield": m.get("dividendYieldIndicatedAnnual"),
        "wk52_high": m.get("52WeekHigh"),
        "wk52_low": m.get("52WeekLow"),
        "sector": profile_body.get("finnhubIndustry") or "",
        "industry": profile_body.get("finnhubIndustry") or "",
        "fetched_at": datetime.now(UTC).isoformat(),
    }


def fetch_fundamentals(ticker: str) -> dict:
    """Cached 24h company fundamentals + sector, from Finnhub. Upserts CompanyFundamentals.

    Returns {} on missing-key or fetch-failure (never raises).
    In mock mode returns a deterministic canned dict.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()

    if is_mock_mode():
        return _canned_fundamentals(ticker)

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("market.fundamentals: no credential configured, skipping fetch")
        return {}

    try:
        metric_body = cache.get_or_fetch(
            f"market:fundamentals:metric:{ticker}",
            ttl_seconds=cache.ttl_for_kind("fundamentals"),
            fetcher=lambda: _finnhub_get(
                "/stock/metric", {"symbol": ticker, "metric": "all"}, api_key
            ),
        )
        profile_body = cache.get_or_fetch(
            f"market:fundamentals:profile:{ticker}",
            ttl_seconds=cache.ttl_for_kind("fundamentals"),
            fetcher=lambda: _finnhub_get("/stock/profile2", {"symbol": ticker}, api_key),
        )
    except Exception as exc:
        log.warning("market.fundamentals.fetch_failed %s: %s", ticker, exc)
        return {}

    normalized = _normalize(ticker, metric_body, profile_body)

    # Upsert the persistent row (best-effort — don't let a DB error surface to caller)
    try:
        from apps.market.models import CompanyFundamentals

        CompanyFundamentals.objects.update_or_create(
            ticker=ticker,
            defaults={
                "sector": normalized.get("sector") or "",
                "industry": normalized.get("industry") or "",
                "metrics": {
                    k: v for k, v in normalized.items() if k not in ("ticker", "fetched_at")
                },
            },
        )
    except Exception as exc:
        log.warning("market.fundamentals.upsert_failed %s: %s", ticker, exc)

    return normalized
