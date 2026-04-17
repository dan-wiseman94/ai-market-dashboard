from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_news_endpoint_returns_items(api):
    items = [
        {"id": 1, "headline": "Hello", "summary": "", "url": "https://x", "source": "R",
         "datetime": 1700000000, "related": "SPY"},
    ]
    with patch("apps.market.views.fetch_news", return_value=items):
        resp = api.get("/api/market/news/?tickers=SPY,AAPL&lookback=24")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["headline"] == "Hello"


@pytest.mark.django_db
def test_news_endpoint_default_lookback_24(api):
    with patch("apps.market.views.fetch_news") as fake:
        fake.return_value = []
        api.get("/api/market/news/?tickers=SPY")
    fake.assert_called_once()
    _, kwargs = fake.call_args
    assert kwargs["lookback_hours"] == 24
