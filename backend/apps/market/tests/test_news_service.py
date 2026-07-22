from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.market.models import NewsItem
from apps.market.services.news import fetch_news


def _resp(items):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = items
    r.raise_for_status = lambda: None
    return r


FINNHUB_SPY = [
    {
        "id": 11,
        "headline": "SPY climbs on Fed minutes",
        "summary": "Markets rally...",
        "url": "https://example.com/1",
        "source": "Reuters",
        "datetime": int(datetime(2026, 4, 17, 9, 12, tzinfo=UTC).timestamp()),
        "related": "SPY",
    },
    {
        "id": 12,
        "headline": "Tech leads gains",
        "summary": "",
        "url": "https://example.com/2",
        "source": "Bloomberg",
        "datetime": int(datetime(2026, 4, 17, 8, 45, tzinfo=UTC).timestamp()),
        "related": "SPY",
    },
]


@pytest.mark.django_db
def test_fetch_news_calls_finnhub_per_ticker_and_dedups():
    with (
        patch("apps.market.services.news._finnhub_get") as fake_get,
        patch("apps.market.services.news._finnhub_api_key", return_value="k"),
        patch("apps.market.services.news.cache.get_or_fetch") as fake_cache,
    ):
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        fake_get.return_value = FINNHUB_SPY
        items = fetch_news(["SPY"])

    assert len(items) == 2
    assert items[0]["headline"] == "SPY climbs on Fed minutes"  # newest first
    assert NewsItem.objects.count() == 2

    # Re-fetch: dedup keeps row count stable.
    with (
        patch("apps.market.services.news._finnhub_get", return_value=FINNHUB_SPY),
        patch("apps.market.services.news._finnhub_api_key", return_value="k"),
        patch("apps.market.services.news.cache.get_or_fetch") as fake_cache,
    ):
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        fetch_news(["SPY"])
    assert NewsItem.objects.count() == 2


@pytest.mark.django_db
def test_fetch_news_no_credential_returns_empty():
    with patch("apps.market.services.news._finnhub_api_key", return_value=None):
        items = fetch_news(["SPY"])
    assert items == []


@pytest.mark.django_db
def test_fetch_news_skips_company_news_for_non_equity():
    # Bare futures roots collide with unrelated equities on Finnhub ("ES" is
    # Eversource) — only equity-like tickers get a company-news call; the
    # market-wide general feed still runs.
    with (
        patch("apps.market.services.news._finnhub_get") as fake_get,
        patch("apps.market.services.news._finnhub_api_key", return_value="k"),
        patch("apps.market.services.news.cache.get_or_fetch") as fake_cache,
    ):
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        fake_get.return_value = []
        fetch_news(["ES", "/NQ", "$SPX", "QQQ"])

    company_calls = [c for c in fake_get.call_args_list if c.args[0] == "/company-news"]
    assert [c.args[1]["symbol"] for c in company_calls] == ["QQQ"]
    assert any(c.args[0] == "/news" for c in fake_get.call_args_list)
