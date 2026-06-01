"""Tests for apps.market.services.alpaca."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import apps.market.services.alpaca as alpaca_mod
from apps.market.services.alpaca import (
    _normalize_bars,
    _normalize_snapshot,
    _persist_bars,
    fetch_bars,
    fetch_quotes,
)

# ---------------------------------------------------------------------------
# Raw Alpaca fixture helpers
# ---------------------------------------------------------------------------

_RAW_SNAPSHOT_AAPL = {
    "latestTrade": {"p": 189.30, "s": 100, "t": "2026-05-30T19:59:00Z"},
    "latestQuote": {"ap": 189.32, "bp": 189.28, "as": 5, "bs": 3},
    "dailyBar": {"o": 188.00, "h": 190.10, "l": 188.45, "c": 189.30, "v": 48_312_100},
    "prevDailyBar": {"o": 187.00, "h": 189.50, "l": 186.50, "c": 187.95},
}

_RAW_SNAPSHOT_MSFT = {
    "latestTrade": {"p": 415.60, "s": 50, "t": "2026-05-30T19:59:00Z"},
    "latestQuote": {"ap": 415.65, "bp": 415.55, "as": 2, "bs": 4},
    "dailyBar": {"o": 413.00, "h": 416.80, "l": 413.90, "c": 415.60, "v": 21_045_000},
    "prevDailyBar": {"o": 414.00, "h": 416.00, "l": 412.00, "c": 416.89},
}

_RAW_SNAPSHOTS_BODY = {
    "AAPL": _RAW_SNAPSHOT_AAPL,
    "MSFT": _RAW_SNAPSHOT_MSFT,
}

_RAW_BARS_BODY = {
    "bars": {
        "AAPL": [
            {
                "t": "2026-05-29T20:00:00Z",
                "o": 188.00,
                "h": 190.50,
                "l": 187.50,
                "c": 189.30,
                "v": 45_000_000,
            },
            {
                "t": "2026-05-30T20:00:00Z",
                "o": 189.30,
                "h": 191.00,
                "l": 188.80,
                "c": 190.75,
                "v": 47_500_000,
            },
        ]
    }
}


# ---------------------------------------------------------------------------
# Unit tests: normalize helpers (no DB, no I/O)
# ---------------------------------------------------------------------------


def test_normalize_snapshot_aapl_quote_fields():
    result = _normalize_snapshot("AAPL", _RAW_SNAPSHOT_AAPL)
    assert result["last"] == 189.30
    assert result["bid"] == 189.28
    assert result["ask"] == 189.32
    assert result["volume"] == 48_312_100
    assert result["high"] == 190.10
    assert result["low"] == 188.45


def test_normalize_snapshot_pct_change_computed_from_daily_vs_prev():
    result = _normalize_snapshot("AAPL", _RAW_SNAPSHOT_AAPL)
    # pct_change = (189.30 - 187.95) / 187.95 * 100
    assert result["pct_change"] is not None
    assert abs(result["pct_change"] - (189.30 - 187.95) / 187.95 * 100) < 0.001


def test_normalize_snapshot_pct_change_none_when_prev_missing():
    blob = {**_RAW_SNAPSHOT_AAPL, "prevDailyBar": {}}
    result = _normalize_snapshot("AAPL", blob)
    assert result["pct_change"] is None


def test_normalize_snapshot_pct_change_none_when_prev_zero():
    blob = {**_RAW_SNAPSHOT_AAPL, "prevDailyBar": {"c": 0}}
    result = _normalize_snapshot("AAPL", blob)
    assert result["pct_change"] is None


def test_normalize_snapshot_volume_is_int():
    result = _normalize_snapshot("AAPL", _RAW_SNAPSHOT_AAPL)
    assert isinstance(result["volume"], int)


def test_normalize_snapshot_missing_sections_return_none():
    result = _normalize_snapshot("XX", {})
    assert result["last"] is None
    assert result["bid"] is None
    assert result["ask"] is None
    assert result["volume"] is None
    assert result["high"] is None
    assert result["low"] is None
    assert result["pct_change"] is None


def test_normalize_bars_maps_alpaca_keys():
    raw = _RAW_BARS_BODY["bars"]["AAPL"]
    result = _normalize_bars(raw)
    assert len(result) == 2
    assert result[0]["open"] == 188.00
    assert result[0]["high"] == 190.50
    assert result[0]["low"] == 187.50
    assert result[0]["close"] == 189.30
    assert result[0]["volume"] == 45_000_000
    assert result[0]["ts"] == "2026-05-29T20:00:00Z"
    assert result[1]["close"] == 190.75


# ---------------------------------------------------------------------------
# Credential helper
# ---------------------------------------------------------------------------


def test_credentials_returns_none_none_on_missing_row():
    with patch.object(alpaca_mod, "decrypt_token", return_value=None):
        key, secret = alpaca_mod._credentials()
    assert key is None
    assert secret is None


def test_credentials_returns_none_none_when_key_missing():
    with patch.object(alpaca_mod, "decrypt_token", return_value={"api_secret": "s"}):
        key, secret = alpaca_mod._credentials()
    assert key is None
    assert secret is None


def test_credentials_returns_none_none_when_secret_missing():
    with patch.object(alpaca_mod, "decrypt_token", return_value={"api_key": "k"}):
        key, secret = alpaca_mod._credentials()
    assert key is None
    assert secret is None


# ---------------------------------------------------------------------------
# fetch_quotes: normalized dict from mocked snapshot response
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_quotes_returns_normalized_dict():
    with (
        patch("apps.market.services.alpaca._credentials", return_value=("k", "s")),
        patch("apps.market.services.alpaca._get", return_value=_RAW_SNAPSHOTS_BODY),
        patch(
            "apps.market.services.alpaca.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fetch_quotes(["AAPL", "MSFT"])

    assert set(result.keys()) == {"AAPL", "MSFT"}

    aapl = result["AAPL"]
    assert aapl["last"] == 189.30
    assert aapl["bid"] == 189.28
    assert aapl["ask"] == 189.32
    assert aapl["volume"] == 48_312_100
    assert aapl["high"] == 190.10
    assert aapl["low"] == 188.45
    assert aapl["pct_change"] is not None

    msft = result["MSFT"]
    assert msft["last"] == 415.60
    assert msft["volume"] == 21_045_000


@pytest.mark.django_db
def test_fetch_quotes_empty_list_returns_empty():
    result = fetch_quotes([])
    assert result == {}


@pytest.mark.django_db
def test_fetch_quotes_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fetch_quotes(["AAPL", "MSFT"])

    assert "AAPL" in result
    assert "MSFT" in result
    aapl = result["AAPL"]
    assert aapl["last"] is not None
    assert isinstance(aapl["volume"], int)


@pytest.mark.django_db
def test_fetch_quotes_no_credential_returns_empty():
    with patch("apps.market.services.alpaca._credentials", return_value=(None, None)):
        result = fetch_quotes(["AAPL"])
    assert result == {}


@pytest.mark.django_db
def test_fetch_quotes_never_raises_on_network_failure():
    with (
        patch("apps.market.services.alpaca._credentials", return_value=("k", "s")),
        patch("apps.market.services.alpaca._get", side_effect=RuntimeError("connection refused")),
        patch(
            "apps.market.services.alpaca.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fetch_quotes(["AAPL"])
    assert result == {}


# ---------------------------------------------------------------------------
# fetch_bars: normalized+persisted bars from mocked response
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_bars_returns_normalized_list():
    with (
        patch("apps.market.services.alpaca._credentials", return_value=("k", "s")),
        patch("apps.market.services.alpaca._get", return_value=_RAW_BARS_BODY),
        patch(
            "apps.market.services.alpaca.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fetch_bars("AAPL", timeframe="1d", limit=60)

    assert len(result) == 2
    assert result[0]["open"] == 188.00
    assert result[0]["close"] == 189.30
    assert result[0]["ts"] == "2026-05-29T20:00:00Z"
    assert result[1]["close"] == 190.75


@pytest.mark.django_db
def test_fetch_bars_persists_ohlcbar_rows():
    from apps.market.models import OHLCBar

    with (
        patch("apps.market.services.alpaca._credentials", return_value=("k", "s")),
        patch("apps.market.services.alpaca._get", return_value=_RAW_BARS_BODY),
        patch(
            "apps.market.services.alpaca.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        fetch_bars("AAPL", timeframe="1d", limit=60)

    rows = list(OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").order_by("ts"))
    assert len(rows) == 2
    assert float(rows[0].close) == 189.30
    assert rows[0].volume == 45_000_000
    assert float(rows[1].close) == 190.75


@pytest.mark.django_db
def test_fetch_bars_idempotent_upsert():
    """Calling fetch_bars twice with the same data must not duplicate OHLCBar rows."""
    from apps.market.models import OHLCBar

    with (
        patch("apps.market.services.alpaca._credentials", return_value=("k", "s")),
        patch("apps.market.services.alpaca._get", return_value=_RAW_BARS_BODY),
        patch(
            "apps.market.services.alpaca.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        fetch_bars("AAPL", timeframe="1d", limit=60)
        fetch_bars("AAPL", timeframe="1d", limit=60)

    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 2


@pytest.mark.django_db
def test_fetch_bars_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fetch_bars("AAPL", timeframe="1d", limit=60)

    assert len(result) == 2
    assert result[0]["open"] is not None
    assert result[0]["ts"] is not None


@pytest.mark.django_db
def test_fetch_bars_no_credential_returns_empty():
    with patch("apps.market.services.alpaca._credentials", return_value=(None, None)):
        result = fetch_bars("AAPL", timeframe="1d")
    assert result == []


@pytest.mark.django_db
def test_fetch_bars_never_raises_on_network_failure():
    with (
        patch("apps.market.services.alpaca._credentials", return_value=("k", "s")),
        patch("apps.market.services.alpaca._get", side_effect=ConnectionError("timeout")),
        patch(
            "apps.market.services.alpaca.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fetch_bars("AAPL", timeframe="1d")
    assert result == []


@pytest.mark.django_db
def test_fetch_bars_unsupported_timeframe_returns_empty():
    with patch("apps.market.services.alpaca._credentials", return_value=("k", "s")):
        result = fetch_bars("AAPL", timeframe="3m")
    assert result == []


# ---------------------------------------------------------------------------
# _persist_bars: standalone idempotency test
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_persist_bars_idempotent_and_updates_on_conflict():
    from apps.market.models import OHLCBar

    bar = {
        "open": 188.00,
        "high": 190.50,
        "low": 187.50,
        "close": 189.30,
        "volume": 45_000_000,
        "ts": "2026-05-29T20:00:00+00:00",
    }
    _persist_bars("AAPL", "1d", [bar])
    _persist_bars("AAPL", "1d", [bar])  # same (ticker, timeframe, ts) → no duplicate
    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 1

    revised = {**bar, "close": 195.0, "volume": 99_999}
    _persist_bars("AAPL", "1d", [revised])  # same key, new values → update in place
    rows = list(OHLCBar.objects.filter(ticker="AAPL", timeframe="1d"))
    assert len(rows) == 1
    assert float(rows[0].close) == 195.0
    assert rows[0].volume == 99_999


@pytest.mark.django_db
def test_persist_bars_skips_rows_with_missing_fields():
    from apps.market.models import OHLCBar

    incomplete = {
        "open": 100.0,
        "high": None,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000,
        "ts": "2026-01-01T00:00:00+00:00",
    }
    _persist_bars("ZZZ", "1d", [incomplete])
    assert OHLCBar.objects.filter(ticker="ZZZ").count() == 0
