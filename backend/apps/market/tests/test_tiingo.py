"""Tests for apps.market.services.tiingo — fetch_daily_bars and fetch_news."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from apps.market.models import NewsItem, OHLCBar
from apps.market.services import tiingo as tiingo_mod

# ---------------------------------------------------------------------------
# Raw API fixture data (mirrors real Tiingo response shapes)
# ---------------------------------------------------------------------------

_RAW_BARS = [
    {
        "date": "2026-01-02T00:00:00+00:00",
        "open": 182.01,
        "high": 185.50,
        "low": 181.23,
        "close": 184.76,
        "volume": 72_000_000,
        "adjClose": 184.76,
        "adjOpen": 182.01,
        "adjHigh": 185.50,
        "adjLow": 181.23,
        "adjVolume": 72_000_000,
        "divCash": 0.0,
        "splitFactor": 1.0,
    },
    {
        "date": "2026-01-03T00:00:00+00:00",
        "open": 184.50,
        "high": 188.00,
        "low": 183.10,
        "close": 187.22,
        "volume": 65_000_000,
        "adjClose": 187.22,
        "adjOpen": 184.50,
        "adjHigh": 188.00,
        "adjLow": 183.10,
        "adjVolume": 65_000_000,
        "divCash": 0.0,
        "splitFactor": 1.0,
    },
]

_RAW_NEWS = [
    {
        "id": 12345,
        "title": "Apple hits record high on strong iPhone sales",
        "description": "AAPL shares climbed 3% after the company reported record iPhone sales.",
        "url": "https://example.com/news/aapl-record",
        "source": "Reuters",
        "publishedDate": "2026-01-03T14:30:00+00:00",
        "tickers": ["aapl", "msft"],
        "tags": ["earnings"],
    },
    {
        "id": 12346,
        "title": "Microsoft Azure revenue beats estimates",
        "description": "Cloud segment grew 28% year-over-year.",
        "url": "https://example.com/news/msft-azure",
        "source": "Bloomberg",
        "publishedDate": "2026-01-02T09:00:00+00:00",
        "tickers": ["msft"],
        "tags": [],
    },
]


_BYPASS_CACHE = lambda key, *, ttl_seconds, fetcher: fetcher()  # noqa: E731


@pytest.mark.django_db
def test_fetch_daily_bars_returns_normalized_bars():
    with (
        patch("apps.market.services.tiingo._api_key", return_value="testkey"),
        patch("apps.market.services.tiingo._get", return_value=_RAW_BARS),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_daily_bars("AAPL")

    assert len(result) == 2

    first = result[0]
    assert first["open"] == 182.01
    assert first["high"] == 185.50
    assert first["low"] == 181.23
    assert first["close"] == 184.76
    assert first["volume"] == 72_000_000
    assert first["ts"] == datetime.fromisoformat("2026-01-02T00:00:00+00:00").isoformat()

    second = result[1]
    assert second["close"] == 187.22
    assert second["volume"] == 65_000_000


@pytest.mark.django_db
def test_fetch_daily_bars_persists_ohlc_rows():
    with (
        patch("apps.market.services.tiingo._api_key", return_value="testkey"),
        patch("apps.market.services.tiingo._get", return_value=_RAW_BARS),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        tiingo_mod.fetch_daily_bars("AAPL")

    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 2
    bar = OHLCBar.objects.get(ticker="AAPL", timeframe="1d", close="184.7600")
    assert bar.volume == 72_000_000


@pytest.mark.django_db
def test_fetch_daily_bars_persist_is_idempotent():
    """Calling fetch_daily_bars twice with the same data must not duplicate rows."""
    with (
        patch("apps.market.services.tiingo._api_key", return_value="testkey"),
        patch("apps.market.services.tiingo._get", return_value=_RAW_BARS),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        tiingo_mod.fetch_daily_bars("AAPL")
        tiingo_mod.fetch_daily_bars("AAPL")

    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 2


@pytest.mark.django_db
def test_fetch_daily_bars_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = tiingo_mod.fetch_daily_bars("AAPL")

    assert isinstance(result, list)
    assert len(result) >= 1
    bar = result[0]
    assert "open" in bar
    assert "high" in bar
    assert "low" in bar
    assert "close" in bar
    assert "volume" in bar
    assert "ts" in bar


@pytest.mark.django_db
def test_fetch_daily_bars_no_credential_returns_empty():
    with patch("apps.market.services.tiingo._api_key", return_value=None):
        result = tiingo_mod.fetch_daily_bars("AAPL")

    assert result == []


@pytest.mark.django_db
def test_fetch_daily_bars_never_raises_on_network_failure():
    def _boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    with (
        patch("apps.market.services.tiingo._api_key", return_value="k"),
        patch("apps.market.services.tiingo._get", side_effect=_boom),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_daily_bars("BOOM")

    assert result == []


@pytest.mark.django_db
def test_fetch_news_returns_normalized_items():
    with (
        patch("apps.market.services.tiingo._api_key", return_value="testkey"),
        patch("apps.market.services.tiingo._get", return_value=_RAW_NEWS),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_news(["AAPL", "MSFT"])

    assert len(result) == 2

    # Newest first: 2026-01-03 before 2026-01-02
    first = result[0]
    assert first["external_id"] == "12345"
    assert first["headline"] == "Apple hits record high on strong iPhone sales"
    assert first["ticker"] == "AAPL"
    assert first["source"] == "Reuters"
    assert first["url"] == "https://example.com/news/aapl-record"
    assert isinstance(first["published_at"], datetime)
    assert first["published_at"].tzinfo is not None

    second = result[1]
    assert second["external_id"] == "12346"
    assert second["ticker"] == "MSFT"


@pytest.mark.django_db
def test_fetch_news_upserts_news_item_rows():
    with (
        patch("apps.market.services.tiingo._api_key", return_value="testkey"),
        patch("apps.market.services.tiingo._get", return_value=_RAW_NEWS),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        tiingo_mod.fetch_news(["AAPL", "MSFT"])

    assert NewsItem.objects.filter(provider="tiingo").count() == 2
    item = NewsItem.objects.get(provider="tiingo", external_id="12345")
    assert item.headline == "Apple hits record high on strong iPhone sales"
    assert item.ticker == "AAPL"
    assert item.source == "Reuters"


@pytest.mark.django_db
def test_fetch_news_upsert_is_idempotent():
    """Calling fetch_news twice with the same items must not duplicate NewsItem rows."""
    with (
        patch("apps.market.services.tiingo._api_key", return_value="testkey"),
        patch("apps.market.services.tiingo._get", return_value=_RAW_NEWS),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        tiingo_mod.fetch_news(["AAPL", "MSFT"])
        tiingo_mod.fetch_news(["AAPL", "MSFT"])

    assert NewsItem.objects.filter(provider="tiingo").count() == 2


@pytest.mark.django_db
def test_fetch_news_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = tiingo_mod.fetch_news(["AAPL"])

    assert isinstance(result, list)
    assert len(result) >= 1
    item = result[0]
    assert "headline" in item
    assert "ticker" in item
    assert "external_id" in item
    assert "published_at" in item


@pytest.mark.django_db
def test_fetch_news_no_credential_returns_empty():
    with patch("apps.market.services.tiingo._api_key", return_value=None):
        result = tiingo_mod.fetch_news(["AAPL"])

    assert result == []


@pytest.mark.django_db
def test_fetch_news_never_raises_on_network_failure():
    def _boom(*args, **kwargs):
        raise RuntimeError("Tiingo news API unavailable")

    with (
        patch("apps.market.services.tiingo._api_key", return_value="k"),
        patch("apps.market.services.tiingo._get", side_effect=_boom),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_news(["AAPL"])

    assert result == []


@pytest.mark.django_db
def test_fetch_news_publisheddate_trailing_z_is_parsed():
    """publishedDate values ending in 'Z' (UTC shorthand) must parse correctly."""
    raw_with_z = [
        {
            "id": 99999,
            "title": "Z-suffix date test",
            "description": "Testing Z suffix handling.",
            "url": "https://example.com/z-test",
            "source": "TestSource",
            "publishedDate": "2026-01-05T10:00:00Z",
            "tickers": ["spy"],
        }
    ]

    with (
        patch("apps.market.services.tiingo._api_key", return_value="k"),
        patch("apps.market.services.tiingo._get", return_value=raw_with_z),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_news(["SPY"])

    assert len(result) == 1
    assert result[0]["published_at"] == datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)
    assert result[0]["ticker"] == "SPY"


@pytest.mark.django_db
def test_fetch_news_respects_limit():
    """Result list must be capped at the requested limit."""
    many_items = [
        {
            "id": i,
            "title": f"Headline {i}",
            "description": "",
            "url": f"https://example.com/{i}",
            "source": "Src",
            "publishedDate": "2026-01-02T00:00:00Z",
            "tickers": ["aapl"],
        }
        for i in range(1, 21)
    ]

    with (
        patch("apps.market.services.tiingo._api_key", return_value="k"),
        patch("apps.market.services.tiingo._get", return_value=many_items),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_news(["AAPL"], limit=5)

    assert len(result) == 5


@pytest.mark.django_db
def test_fetch_daily_bars_skips_bars_with_missing_fields():
    """Bars missing required fields are silently skipped."""
    raw_with_nulls = [
        {
            "date": "2026-01-02T00:00:00+00:00",
            "open": None,
            "high": 185.50,
            "low": 181.23,
            "close": 184.76,
            "volume": 72_000_000,
        },
        {
            "date": "2026-01-03T00:00:00+00:00",
            "open": 184.50,
            "high": 188.00,
            "low": 183.10,
            "close": 187.22,
            "volume": 65_000_000,
        },
    ]

    with (
        patch("apps.market.services.tiingo._api_key", return_value="k"),
        patch("apps.market.services.tiingo._get", return_value=raw_with_nulls),
        patch("apps.market.services.tiingo.cache.get_or_fetch", side_effect=_BYPASS_CACHE),
    ):
        result = tiingo_mod.fetch_daily_bars("AAPL")

    assert len(result) == 1
    assert result[0]["close"] == 187.22
