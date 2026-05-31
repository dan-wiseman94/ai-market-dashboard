"""Live macro-economic series from the FRED (St. Louis Fed) API.

Sourced from api.stlouisfed.org (free, requires a free API key):
- GET /series/observations?series_id=<ID>&sort_order=desc&limit=2

Each series is cached independently with a 6-hour TTL.  Per-series failures are
isolated — one bad series never kills the rest.  Never raises; returns {} on all
failures.
"""

from __future__ import annotations

import logging

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.services.safe_log import safe_err
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"

# Curated set of FRED series to fetch by default.
# Deliberately includes the full Treasury yield-curve tenors so the yield curve
# is covered in a single macro section.
SERIES: dict[str, str] = {
    "CPIAUCSL": "CPI",
    "UNRATE": "Unemployment rate",
    "FEDFUNDS": "Fed funds rate",
    "PAYEMS": "Nonfarm payrolls",
    "GDPC1": "Real GDP",
    "DGS1MO": "1M yield",
    "DGS3MO": "3M yield",
    "DGS2": "2Y yield",
    "DGS5": "5Y yield",
    "DGS10": "10Y yield",
    "DGS30": "30Y yield",
    "T10Y2Y": "10Y-2Y spread",
    "VIXCLS": "VIX",
    "DTWEXBGS": "Dollar index",
    "MORTGAGE30US": "30Y mortgage",
}


def _api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="fred")
    except ApiCredential.DoesNotExist:
        return None
    return (cred.token or {}).get("api_key")


def _get(path: str, params: dict) -> dict:
    resp = requests.get(f"{FRED_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def _canned_macro() -> dict:
    """Deterministic fixture for MOCK_EXTERNAL / e2e mode."""
    return {
        "CPIAUCSL": {
            "label": "CPI",
            "value": 314.5,
            "date": "2025-04-01",
            "prev": 313.8,
            "change": 0.7,
        },
        "DGS10": {
            "label": "10Y yield",
            "value": 4.32,
            "date": "2025-05-28",
            "prev": 4.28,
            "change": 0.04,
        },
    }


def _parse_value(raw: str) -> float | None:
    """Return float or None for FRED's missing-data sentinel '.'."""
    if raw == ".":
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _fetch_series(sid: str, api_key: str) -> dict:
    """Fetch the two most recent observations for one FRED series via cache."""
    body = cache.get_or_fetch(
        f"market:fred:{sid}",
        ttl_seconds=cache.ttl_for_kind("macro"),
        fetcher=lambda: _get(
            "/series/observations",
            {
                "series_id": sid,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,
            },
        ),
    )
    return body


def _normalize_series(sid: str, body: dict) -> dict:
    """Build the per-series dict from a raw FRED observations response."""
    label = SERIES.get(sid, sid)
    observations = body.get("observations") or []

    value: float | None = None
    date: str = ""
    prev: float | None = None

    if len(observations) >= 1:
        value = _parse_value(observations[0].get("value", "."))
        date = observations[0].get("date", "")
    if len(observations) >= 2:
        prev = _parse_value(observations[1].get("value", "."))

    change: float | None = None
    if value is not None and prev is not None:
        change = value - prev

    return {
        "label": label,
        "value": value,
        "date": date,
        "prev": prev,
        "change": change,
    }


def fetch_macro(series_ids: list[str] | None = None) -> dict:
    """Fetch curated FRED macro series; return normalized dict keyed by series ID.

    Each series is cached independently (key ``market:fred:<sid>``, 6-hour TTL).
    Per-series failures are isolated — one series failing or raising does not affect
    the others.  Returns {} only if no series succeed.

    In mock mode returns a deterministic canned dict for a couple of series.
    Missing credential → {}.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _canned_macro()

    api_key = _api_key()
    if not api_key:
        log.info("market.fred: no credential configured, skipping")
        return {}

    ids = series_ids if series_ids is not None else list(SERIES.keys())
    result: dict = {}

    for sid in ids:
        try:
            body = _fetch_series(sid, api_key)
            result[sid] = _normalize_series(sid, body)
        except Exception as exc:
            log.warning("market.fred.fetch_series_failed sid=%s: %s", sid, safe_err(exc))

    return result
