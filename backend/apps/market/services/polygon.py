"""Daily OHLC bars and previous-close via Polygon.io (free tier, end-of-day only).

Endpoints used:
- GET /v2/aggs/ticker/<T>/range/1/day/<from>/<to>  — daily aggregates, up to 120 bars
- GET /v2/aggs/ticker/<T>/prev                     — previous session close

Cached at ohlc_1d TTL (3600 s). Persists bars to OHLCBar via _persist_bars.
Never raises — returns [] / None on any failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.services._bars import persist_bars
from apps.market.services.safe_log import safe_err
from apps.secrets.credentials import decrypt_token

log = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"


def _api_key() -> str | None:
    return (decrypt_token("polygon") or {}).get("api_key")


def _get(path: str, params: dict, api_key: str) -> dict:
    p = {**params, "apiKey": api_key}
    resp = requests.get(f"{POLYGON_BASE}{path}", params=p, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# OHLCBar persist helper (canonical shape from spec)
# ---------------------------------------------------------------------------


def _persist_bars(ticker: str, timeframe: str, bars: list[dict]) -> None:
    persist_bars(ticker, timeframe, bars, source="polygon")


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_bar(raw: dict) -> dict:
    """Convert one Polygon aggregate result dict to the bars contract."""
    t_ms = raw.get("t", 0)
    ts = datetime.fromtimestamp(t_ms / 1000, tz=UTC).isoformat()
    return {
        "open": raw.get("o"),
        "high": raw.get("h"),
        "low": raw.get("l"),
        "close": raw.get("c"),
        "volume": raw.get("v"),
        "ts": ts,
    }


def _normalize_prev_close(raw: dict) -> dict | None:
    """Return prev-close dict from a /prev response, or None if no results."""
    results = raw.get("results") or []
    if not results:
        return None
    r = results[0]
    t_ms = r.get("t", 0)
    return {
        "open": r.get("o"),
        "high": r.get("h"),
        "low": r.get("l"),
        "close": r.get("c"),
        "volume": r.get("v"),
        "ts": datetime.fromtimestamp(t_ms / 1000, tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Canned fixtures for MOCK_EXTERNAL / e2e mode
# ---------------------------------------------------------------------------


def _canned_daily_bars(ticker: str) -> list[dict]:
    """Deterministic fixture: two daily bars for any ticker."""
    base_ts_ms = 1_700_000_000_000
    return [
        {
            "open": 150.0,
            "high": 155.0,
            "low": 149.0,
            "close": 153.0,
            "volume": 80_000_000,
            "ts": datetime.fromtimestamp(base_ts_ms / 1000, tz=UTC).isoformat(),
        },
        {
            "open": 153.0,
            "high": 157.0,
            "low": 152.0,
            "close": 156.0,
            "volume": 85_000_000,
            "ts": datetime.fromtimestamp((base_ts_ms + 86_400_000) / 1000, tz=UTC).isoformat(),
        },
    ]


def _canned_prev_close(ticker: str) -> dict:
    """Deterministic fixture for previous-close."""
    return {
        "open": 153.0,
        "high": 157.0,
        "low": 152.0,
        "close": 156.0,
        "volume": 85_000_000,
        "ts": datetime.fromtimestamp(1_700_086_400, tz=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def fetch_daily_bars(ticker: str, *, days: int = 120) -> list[dict]:
    """Fetch and persist up to `days` daily OHLC bars from Polygon.io.

    Results are stored in OHLCBar (timeframe="1d") and returned as a list
    of bar dicts (oldest → newest).  Returns [] on missing credential or
    any fetch failure (never raises).
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()

    if is_mock_mode():
        return _canned_daily_bars(ticker)

    api_key = _api_key()
    if not api_key:
        log.info("market.polygon: no credential configured, skipping fetch_daily_bars")
        return []

    to_date = date.today()
    from_date = to_date - timedelta(days=days)

    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    # Request RAW (unadjusted) bars: returns.py corrects splits itself and
    # assumes OHLCBar holds raw prices. adjusted="true" would double-correct.
    params = {"adjusted": "false", "sort": "asc", "limit": 120}

    try:
        body = cache.get_or_fetch(
            f"market:polygon:daily:{ticker}:{from_date}:{to_date}",
            ttl_seconds=cache.ttl_for_kind("ohlc_1d"),
            fetcher=lambda: _get(path, params, api_key),
        )
    except Exception as exc:
        log.warning("market.polygon.fetch_daily_bars ticker=%s: %s", ticker, safe_err(exc))
        return []

    results = body.get("results") or []
    bars = [_normalize_bar(r) for r in results]
    _persist_bars(ticker, "1d", bars)
    return bars


def fetch_prev_close(ticker: str) -> dict | None:
    """Fetch the previous session close from Polygon.io.

    Returns a single dict with open/high/low/close/volume/ts, or None on
    missing credential, missing data, or any fetch failure (never raises).
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()

    if is_mock_mode():
        return _canned_prev_close(ticker)

    api_key = _api_key()
    if not api_key:
        log.info("market.polygon: no credential configured, skipping fetch_prev_close")
        return None

    path = f"/v2/aggs/ticker/{ticker}/prev"
    params: dict = {"adjusted": "false"}  # raw bars — see fetch_daily_bars note

    try:
        body = cache.get_or_fetch(
            f"market:polygon:prev:{ticker}",
            ttl_seconds=cache.ttl_for_kind("ohlc_1d"),
            fetcher=lambda: _get(path, params, api_key),
        )
    except Exception as exc:
        log.warning("market.polygon.fetch_prev_close ticker=%s: %s", ticker, safe_err(exc))
        return None

    return _normalize_prev_close(body)
