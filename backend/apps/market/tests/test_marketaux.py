"""Tests for fetch_news from the Marketaux service."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from apps.market.models import NewsItem
from apps.market.services import marketaux as marketaux_mod

_PUBLISHED_1 = "2026-04-17T09:30:00Z"
_PUBLISHED_2 = "2026-04-17T08:15:00Z"


def _raw_item(
    uuid="uuid-aapl-1",
    title="AAPL Surges On Earnings Beat",
    description="Apple reported strong Q2 results.",
    snippet=None,
    url="https://example.com/aapl-1",
    source="Reuters",
    published_at=_PUBLISHED_1,
    entities=None,
):
    if entities is None:
        entities = [
            {"symbol": "AAPL", "sentiment_score": 0.75, "type": "equity"},
            {"symbol": "MSFT", "sentiment_score": 0.20, "type": "equity"},
        ]
    return {
        "uuid": uuid,
        "title": title,
        "description": description,
        "snippet": snippet,
        "url": url,
        "source": source,
        "published_at": published_at,
        "entities": entities,
    }


def _raw_response(items: list[dict]) -> dict:
    return {"data": items, "meta": {"found": len(items), "returned": len(items)}}


@pytest.mark.django_db
def test_fetch_news_returns_normalized_items_with_sentiment():
    item1 = _raw_item()
    item2 = _raw_item(
        uuid="uuid-msft-1",
        title="MSFT Cloud Revenue Climbs",
        description="Azure growth accelerates.",
        url="https://example.com/msft-1",
        source="Bloomberg",
        published_at=_PUBLISHED_2,
        entities=[{"symbol": "MSFT", "sentiment_score": -0.15, "type": "equity"}],
    )
    raw_response = _raw_response([item1, item2])

    with (
        patch("apps.market.services.marketaux._api_key", return_value="testkey"),
        patch("apps.market.services.marketaux._get", return_value=raw_response),
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        results = marketaux_mod.fetch_news(["AAPL", "MSFT"], limit=15)

    assert len(results) == 2

    # Newest first
    first = results[0]
    assert first["external_id"] == "uuid-aapl-1"
    assert first["headline"] == "AAPL Surges On Earnings Beat"
    assert first["summary"] == "Apple reported strong Q2 results."
    assert first["url"] == "https://example.com/aapl-1"
    assert first["source"] == "Reuters"
    assert isinstance(first["published_at"], datetime)
    assert first["published_at"].tzinfo is not None

    assert "AAPL" in first["tickers"]
    assert "MSFT" in first["tickers"]

    assert first["sentiment"]["AAPL"] == pytest.approx(0.75)
    assert first["sentiment"]["MSFT"] == pytest.approx(0.20)

    second = results[1]
    assert second["external_id"] == "uuid-msft-1"
    assert second["sentiment"]["MSFT"] == pytest.approx(-0.15)


@pytest.mark.django_db
def test_fetch_news_upsert_idempotency():
    item = _raw_item()
    raw_response = _raw_response([item])

    def _run():
        with (
            patch("apps.market.services.marketaux._api_key", return_value="k"),
            patch("apps.market.services.marketaux._get", return_value=raw_response),
            patch(
                "apps.market.services.marketaux.cache.get_or_fetch",
                side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
            ),
        ):
            marketaux_mod.fetch_news(["AAPL"])

    _run()
    _run()  # second call must not create a duplicate row

    assert NewsItem.objects.filter(provider="marketaux", external_id="uuid-aapl-1").count() == 1
    row = NewsItem.objects.get(provider="marketaux", external_id="uuid-aapl-1")
    assert row.headline == "AAPL Surges On Earnings Beat"
    assert row.ticker == "AAPL"


def test_fetch_news_chunking_calls_get_multiple_times():
    """Six tickers → two chunks of 3 → _get called twice."""
    raw_resp = _raw_response([])

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", return_value=raw_resp) as mock_get,
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        marketaux_mod.fetch_news(["AAPL", "MSFT", "GOOG", "AMZN", "META", "TSLA"])

    assert mock_get.call_count == 2


def test_fetch_news_exactly_three_tickers_is_one_chunk():
    """Exactly 3 tickers → single _get call."""
    raw_resp = _raw_response([])

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", return_value=raw_resp) as mock_get,
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        marketaux_mod.fetch_news(["AAPL", "MSFT", "GOOG"])

    assert mock_get.call_count == 1


def test_fetch_news_four_tickers_splits_into_two_chunks():
    """4 tickers → chunk [3] + [1] → _get called twice."""
    raw_resp = _raw_response([])

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", return_value=raw_resp) as mock_get,
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        marketaux_mod.fetch_news(["AAPL", "MSFT", "GOOG", "AMZN"])

    assert mock_get.call_count == 2


def test_fetch_news_mock_mode_returns_canned_list():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        results = marketaux_mod.fetch_news(["AAPL"])

    assert isinstance(results, list)
    assert len(results) >= 1
    first = results[0]
    assert "external_id" in first
    assert "headline" in first
    assert "sentiment" in first
    assert isinstance(first["sentiment"], dict)
    assert len(first["sentiment"]) >= 1
    for sym, score in first["sentiment"].items():
        assert isinstance(sym, str)
        assert isinstance(score, float)


def test_fetch_news_no_credential_returns_empty():
    with patch("apps.market.services.marketaux._api_key", return_value=None):
        result = marketaux_mod.fetch_news(["AAPL"])
    assert result == []


def test_fetch_news_network_error_returns_empty():
    def _boom(path, params):
        raise OSError("connection refused")

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", side_effect=_boom),
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = marketaux_mod.fetch_news(["AAPL"])

    assert result == []


@pytest.mark.django_db
def test_fetch_news_uses_snippet_when_description_absent():
    item = _raw_item(description=None, snippet="Snippet text here.")
    raw_response = _raw_response([item])

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", return_value=raw_response),
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        results = marketaux_mod.fetch_news(["AAPL"])

    assert results[0]["summary"] == "Snippet text here."


@pytest.mark.django_db
def test_fetch_news_deduplicates_across_chunks():
    """Same uuid returned from two chunks is included only once."""
    duplicate = _raw_item()
    resp = _raw_response([duplicate])

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", return_value=resp),
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        # 4 tickers → 2 chunks, both return same item
        results = marketaux_mod.fetch_news(["AAPL", "MSFT", "GOOG", "AMZN"])

    uuids = [r["external_id"] for r in results]
    assert uuids.count("uuid-aapl-1") == 1


@pytest.mark.django_db
def test_fetch_news_limit_caps_results():
    items = [
        _raw_item(
            uuid=f"uuid-{i}",
            title=f"Headline {i}",
            published_at=f"2026-04-17T0{i}:00:00Z",
            entities=[{"symbol": "AAPL", "sentiment_score": 0.1}],
        )
        for i in range(5)
    ]
    raw_response = _raw_response(items)

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch("apps.market.services.marketaux._get", return_value=raw_response),
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        results = marketaux_mod.fetch_news(["AAPL"], limit=3)

    assert len(results) == 3


def test_fetch_news_empty_tickers_returns_empty():
    with patch("apps.market.services.marketaux._api_key", return_value="k"):
        result = marketaux_mod.fetch_news([])
    assert result == []
