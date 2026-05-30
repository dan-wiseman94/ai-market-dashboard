"""Tests for CompanyFundamentals model."""

import pytest
from django.db import IntegrityError

from apps.market.models import CompanyFundamentals


@pytest.mark.django_db
def test_company_fundamentals_create():
    obj = CompanyFundamentals.objects.create(
        ticker="AAPL",
        sector="Technology",
        industry="Consumer Electronics",
        metrics={"pe": 28.5, "eps_ttm": 6.42},
    )
    assert obj.pk is not None
    assert obj.ticker == "AAPL"
    assert obj.sector == "Technology"
    assert obj.industry == "Consumer Electronics"
    assert obj.metrics["pe"] == 28.5
    assert obj.fetched_at is not None


@pytest.mark.django_db
def test_company_fundamentals_unique_ticker_constraint():
    CompanyFundamentals.objects.create(
        ticker="NVDA",
        sector="Technology",
        industry="Semiconductors",
        metrics={},
    )
    with pytest.raises(IntegrityError):
        CompanyFundamentals.objects.create(
            ticker="NVDA",
            sector="Technology",
            industry="Semiconductors",
            metrics={},
        )


@pytest.mark.django_db
def test_company_fundamentals_update_or_create_upserts():
    CompanyFundamentals.objects.update_or_create(
        ticker="TSLA",
        defaults={"sector": "Consumer Cyclical", "industry": "Auto", "metrics": {"pe": 60.0}},
    )
    CompanyFundamentals.objects.update_or_create(
        ticker="TSLA",
        defaults={"sector": "Consumer Cyclical", "industry": "Auto", "metrics": {"pe": 55.0}},
    )
    assert CompanyFundamentals.objects.filter(ticker="TSLA").count() == 1
    obj = CompanyFundamentals.objects.get(ticker="TSLA")
    assert obj.metrics["pe"] == 55.0
