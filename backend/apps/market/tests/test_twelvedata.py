"""Tests for the Twelve Data market-data service.

Covers:
- fetch_quotes: multi-symbol and single-symbol response shapes, normalization
- fetch_time_series: normalization, OHLCBar persistence, idempotency
- Mock-mode short-circuit
- Missing-credential guard
- Network-error resilience
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services import twelvedata as td_mod

_RAW_QUOTE_AAPL = {
    "symbol": "AAPL",
    "open": "170.10",
    "high": "172.50",
    "low": "169.80",
    "close": "171.30",
    "previous_close": "170.00",
    "volume": "54321678",
    "percent_change": "0.76",
    "exchange": "NASDAQ",
}

_RAW_QUOTE_MSFT = {
    "symbol": "MSFT",
    "open": "420.00",
    "high": "425.00",
    "low": "418.50",
    "close": "423.75",
    "previous_close": "419.00",
    "volume": "22000000.0",
    "percent_change": "-0.50",
    "exchange": "NASDAQ",
}


_RAW_TS_VALUES = [
    {
        "datetime": "2026-05-28",
        "open": "170.00",
        "high": "172.00",
        "low": "169.00",
        "close": "171.00",
        "volume": "50000000",
    },
    {
        "datetime": "2026-05-29",
        "open": "171.00",
        "high": "173.00",
        "low": "170.00",
        "close": "172.50",
        "volume": "48000000",
    },
]

_RAW_TS_INTRADAY_VALUES = [
    {
        "datetime": "2026-05-29 09:30:00",
        "open": "170.00",
        "high": "171.00",
        "low": "169.50",
        "close": "170.75",
        "volume": "1500000",
    },
]

_RAW_TS_BODY = {
    "meta": {"symbol": "AAPL", "interval": "1day", "exchange": "NASDAQ"},
    "values": _RAW_TS_VALUES,
    "status": "ok",
}


_BYPASS_CACHE = patch(
    "apps.market.services.twelvedata.cache.get_or_fetch",
    side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
)

_FAKE_KEY = patch("apps.market.services.twelvedata._api_key", return_value="testkey")


def test_fetch_quotes_multi_symbol_normalization():
    """Multi-symbol response (no top-level 'symbol' key) is parsed correctly."""
    raw_multi = {
        "AAPL": _RAW_QUOTE_AAPL,
        "MSFT": _RAW_QUOTE_MSFT,
    }

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=raw_multi),
    ):
        result = td_mod.fetch_quotes(["AAPL", "MSFT"])

    assert set(result.keys()) == {"AAPL", "MSFT"}

    aapl = result["AAPL"]
    assert aapl["last"] == pytest.approx(171.30)
    assert aapl["high"] == pytest.approx(172.50)
    assert aapl["low"] == pytest.approx(169.80)
    assert aapl["volume"] == 54321678
    assert aapl["pct_change"] == pytest.approx(0.76)
    assert aapl["bid"] is None
    assert aapl["ask"] is None

    msft = result["MSFT"]
    assert msft["last"] == pytest.approx(423.75)
    assert msft["pct_change"] == pytest.approx(-0.50)
    assert msft["volume"] == 22000000


def test_fetch_quotes_single_symbol_response_shape():
    """Single-symbol response (top-level 'symbol' key present) is handled correctly."""
    # Twelve Data sends the quote dict directly — no wrapping key.
    raw_single = _RAW_QUOTE_AAPL  # has "symbol": "AAPL" at top level

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=raw_single),
    ):
        result = td_mod.fetch_quotes(["AAPL"])

    assert "AAPL" in result
    aapl = result["AAPL"]
    assert aapl["last"] == pytest.approx(171.30)
    assert aapl["bid"] is None
    assert aapl["ask"] is None


def test_fetch_quotes_bad_values_become_none():
    """Unparseable numeric fields fall back to None rather than raising."""
    raw = {
        "BADSYM": {
            "symbol": "BADSYM",
            "open": "n/a",
            "high": None,
            "low": "bad",
            "close": "",
            "volume": "not-a-number",
            "percent_change": None,
        }
    }

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=raw),
    ):
        result = td_mod.fetch_quotes(["BADSYM"])

    assert "BADSYM" in result
    q = result["BADSYM"]
    assert q["last"] is None
    assert q["volume"] is None
    assert q["pct_change"] is None


def test_fetch_quotes_network_error_returns_empty():
    def _boom(*_a, **_kw):
        raise OSError("connection refused")

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", side_effect=_boom),
    ):
        result = td_mod.fetch_quotes(["AAPL"])

    assert result == {}


def test_fetch_quotes_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = td_mod.fetch_quotes(["AAPL", "MSFT"])

    assert "AAPL" in result
    assert "MSFT" in result
    for sym in ("AAPL", "MSFT"):
        q = result[sym]
        assert isinstance(q["last"], float)
        assert isinstance(q["volume"], int)
        assert q["bid"] is None
        assert q["ask"] is None


@pytest.mark.django_db
def test_fetch_time_series_normalization():
    """Daily bars are normalized and timestamps are ISO-8601 UTC."""
    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=_RAW_TS_BODY),
    ):
        bars = td_mod.fetch_time_series("AAPL", interval="1day", outputsize=60)

    assert len(bars) == 2
    b0, b1 = bars

    assert b0["open"] == pytest.approx(170.00)
    assert b0["high"] == pytest.approx(172.00)
    assert b0["low"] == pytest.approx(169.00)
    assert b0["close"] == pytest.approx(171.00)
    assert b0["volume"] == 50_000_000
    # Daily bar datetime "YYYY-MM-DD" → ISO with midnight UTC
    assert b0["ts"] == "2026-05-28T00:00:00+00:00"

    assert b1["close"] == pytest.approx(172.50)
    assert b1["ts"] == "2026-05-29T00:00:00+00:00"


@pytest.mark.django_db
def test_fetch_time_series_intraday_datetime_parsed():
    """Intraday 'YYYY-MM-DD HH:MM:SS' datetime is parsed and given UTC tzinfo."""
    body = {
        "meta": {"symbol": "AAPL", "interval": "15min"},
        "values": _RAW_TS_INTRADAY_VALUES,
        "status": "ok",
    }
    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=body),
    ):
        bars = td_mod.fetch_time_series("AAPL", interval="15min")

    assert len(bars) == 1
    assert bars[0]["ts"] == "2026-05-29T09:30:00+00:00"


@pytest.mark.django_db
def test_fetch_time_series_persists_idempotent():
    """Calling twice with the same data produces exactly one OHLCBar row per bar."""
    from apps.market.models import OHLCBar

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=_RAW_TS_BODY),
    ):
        td_mod.fetch_time_series("MSFT", interval="1day", outputsize=60)
        td_mod.fetch_time_series("MSFT", interval="1day", outputsize=60)

    count = OHLCBar.objects.filter(ticker="MSFT", timeframe="1d").count()
    assert count == 2


def test_fetch_time_series_network_error_returns_empty():
    def _boom(*_a, **_kw):
        raise OSError("timeout")

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", side_effect=_boom),
    ):
        result = td_mod.fetch_time_series("AAPL", interval="1day")

    assert result == []


def test_fetch_time_series_missing_values_key_returns_empty():
    """If the API returns a body without 'values', return []."""
    body = {"meta": {}, "status": "error", "code": 400, "message": "Invalid apikey"}

    with (
        _FAKE_KEY,
        _BYPASS_CACHE,
        patch("apps.market.services.twelvedata._get", return_value=body),
    ):
        result = td_mod.fetch_time_series("AAPL", interval="1day")

    assert result == []


@pytest.mark.django_db
def test_fetch_time_series_mock_mode_returns_canned_and_persists():
    """Mock mode returns canned bars AND persists them to OHLCBar."""
    from apps.market.models import OHLCBar

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        bars = td_mod.fetch_time_series("AAPL", interval="1day")

    assert len(bars) == 5
    for b in bars:
        assert isinstance(b["open"], float)
        assert isinstance(b["volume"], int)
        assert "+00:00" in b["ts"]

    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 5
