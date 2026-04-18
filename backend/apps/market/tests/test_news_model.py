from datetime import UTC, datetime

import pytest
from django.db import IntegrityError

from apps.market.models import NewsItem


@pytest.mark.django_db
def test_newsitem_unique_per_provider_external_id():
    NewsItem.objects.create(
        provider="finnhub", external_id="abc123",
        ticker="SPY", headline="Fed minutes", url="https://example.com/1",
        source="Reuters",
        published_at=datetime(2026, 4, 17, 9, 12, tzinfo=UTC),
    )
    with pytest.raises(IntegrityError):
        NewsItem.objects.create(
            provider="finnhub", external_id="abc123",
            ticker="SPY", headline="dup", url="https://example.com/1",
            source="Reuters",
            published_at=datetime(2026, 4, 17, 9, 12, tzinfo=UTC),
        )


@pytest.mark.django_db
def test_newsitem_blank_ticker_for_market_wide_news():
    n = NewsItem.objects.create(
        provider="finnhub", external_id="market1",
        ticker="", headline="Market-wide", url="https://example.com/m",
        source="Bloomberg",
        published_at=datetime(2026, 4, 17, 8, 0, tzinfo=UTC),
    )
    assert n.ticker == ""
