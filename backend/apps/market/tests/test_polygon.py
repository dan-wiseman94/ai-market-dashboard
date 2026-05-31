"""Tests for the Polygon.io service (fetch_daily_bars, fetch_prev_close)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from apps.market.models import OHLCBar
from apps.market.services import polygon as polygon_mod

# ---------------------------------------------------------------------------
# Raw Polygon API response fixtures
# ---------------------------------------------------------------------------

_T1_MS = 1_700_000_000_000  # 2023-11-14 22:13:20 UTC
_T2_MS = _T1_MS + 86_400_000  # + 1 day

_RAW_AGGS_BODY = {
    "status": "OK",
    "resultsCount": 2,
    "results": [
        {"t": _T1_MS, "o": 150.0, "h": 155.0, "l": 149.0, "c": 153.0, "v": 80_000_000},
        {"t": _T2_MS, "o": 153.0, "h": 157.0, "l": 152.0, "c": 156.0, "v": 85_000_000},
    ],
}

_RAW_PREV_BODY = {
    "status": "OK",
    "resultsCount": 1,
    "results": [
        {"t": _T2_MS, "o": 153.0, "h": 157.0, "l": 152.0, "c": 156.0, "v": 85_000_000},
    ],
}

_RAW_EMPTY_BODY = {"status": "OK", "resultsCount": 0}


# ---------------------------------------------------------------------------
# 1. Normalized daily bars — correct field mapping + value types
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_daily_bars_returns_normalized_list():
    with (
        patch("apps.market.services.polygon._api_key", return_value="testkey"),
        patch("apps.market.services.polygon._get", return_value=_RAW_AGGS_BODY),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        bars = polygon_mod.fetch_daily_bars("AAPL", days=120)

    assert len(bars) == 2

    b0 = bars[0]
    assert b0["open"] == 150.0
    assert b0["high"] == 155.0
    assert b0["low"] == 149.0
    assert b0["close"] == 153.0
    assert b0["volume"] == 80_000_000
    assert b0["ts"] == datetime.fromtimestamp(_T1_MS / 1000, tz=UTC).isoformat()

    b1 = bars[1]
    assert b1["close"] == 156.0
    assert b1["ts"] == datetime.fromtimestamp(_T2_MS / 1000, tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# 2. Normalized + persisted — OHLCBar rows are created, idempotent on 2nd call
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_daily_bars_upserts_ohlcbar_rows_idempotent():
    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", return_value=_RAW_AGGS_BODY),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        polygon_mod.fetch_daily_bars("TSLA", days=120)
        polygon_mod.fetch_daily_bars("TSLA", days=120)  # idempotent second call

    assert OHLCBar.objects.filter(ticker="TSLA", timeframe="1d").count() == 2

    bar = OHLCBar.objects.get(
        ticker="TSLA",
        timeframe="1d",
        ts=datetime.fromtimestamp(_T1_MS / 1000, tz=UTC),
    )
    assert float(bar.open) == 150.0
    assert float(bar.close) == 153.0
    assert bar.volume == 80_000_000


# ---------------------------------------------------------------------------
# 3. prev_close — correct field mapping
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_prev_close_returns_dict():
    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", return_value=_RAW_PREV_BODY),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = polygon_mod.fetch_prev_close("AAPL")

    assert result is not None
    assert result["open"] == 153.0
    assert result["high"] == 157.0
    assert result["low"] == 152.0
    assert result["close"] == 156.0
    assert result["volume"] == 85_000_000
    assert result["ts"] == datetime.fromtimestamp(_T2_MS / 1000, tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# 4. prev_close — missing results → None
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_prev_close_returns_none_when_no_results():
    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", return_value=_RAW_EMPTY_BODY),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = polygon_mod.fetch_prev_close("UNKNOWN")

    assert result is None


# ---------------------------------------------------------------------------
# 5. Mock mode — canned fixtures, no real API call
# ---------------------------------------------------------------------------


def test_fetch_daily_bars_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        bars = polygon_mod.fetch_daily_bars("ANYTHING")

    assert isinstance(bars, list)
    assert len(bars) == 2
    assert all(k in bars[0] for k in ("open", "high", "low", "close", "volume", "ts"))
    assert bars[0]["close"] == 153.0
    assert bars[1]["close"] == 156.0


def test_fetch_prev_close_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = polygon_mod.fetch_prev_close("ANYTHING")

    assert result is not None
    assert result["close"] == 156.0
    assert "ts" in result


# ---------------------------------------------------------------------------
# 6. Missing credential → empty / None (never raises)
# ---------------------------------------------------------------------------


def test_fetch_daily_bars_no_credential_returns_empty():
    with patch("apps.market.services.polygon._api_key", return_value=None):
        result = polygon_mod.fetch_daily_bars("AAPL")

    assert result == []


def test_fetch_prev_close_no_credential_returns_none():
    with patch("apps.market.services.polygon._api_key", return_value=None):
        result = polygon_mod.fetch_prev_close("AAPL")

    assert result is None


# ---------------------------------------------------------------------------
# 7. Network failure → empty / None (never raises)
# ---------------------------------------------------------------------------


def test_fetch_daily_bars_never_raises_on_network_failure():
    def _boom(path, params, api_key):
        raise RuntimeError("connection refused")

    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", side_effect=_boom),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = polygon_mod.fetch_daily_bars("BOOM")

    assert result == []


def test_fetch_prev_close_never_raises_on_network_failure():
    def _boom(path, params, api_key):
        raise RuntimeError("timeout")

    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", side_effect=_boom),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = polygon_mod.fetch_prev_close("BOOM")

    assert result is None


# ---------------------------------------------------------------------------
# 8. daily bars with missing "results" key → empty list (no KeyError)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_daily_bars_handles_missing_results_key():
    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", return_value={"status": "OK"}),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = polygon_mod.fetch_daily_bars("AAPL")

    assert result == []
