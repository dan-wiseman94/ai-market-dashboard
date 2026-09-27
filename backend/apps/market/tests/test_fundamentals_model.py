"""Tests for CompanyFundamentals model."""

import pytest
from django.db import IntegrityError

from apps.market.models import CompanyFundamentals


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
