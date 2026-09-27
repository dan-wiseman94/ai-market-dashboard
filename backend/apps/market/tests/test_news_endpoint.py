from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_news_endpoint_returns_items(api):
    items = [
        {
            "id": 1,
            "headline": "Hello",
            "summary": "",
            "url": "https://x",
            "source": "R",
            "datetime": 1700000000,
            "related": "SPY",
        },
    ]
    with patch("apps.market.views.fetch_news", return_value=items):
        resp = api.get("/api/market/news/?tickers=SPY,AAPL&lookback_hours=24")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["headline"] == "Hello"


@pytest.mark.django_db
def test_news_endpoint_invalid_lookback_hours_returns_400(api):
    resp = api.get("/api/market/news/?tickers=SPY&lookback_hours=abc")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_lookback_hours"
