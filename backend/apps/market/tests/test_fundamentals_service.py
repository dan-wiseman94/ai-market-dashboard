"""Tests for fetch_fundamentals service."""

from unittest.mock import patch

import pytest

from apps.market.models import CompanyFundamentals
from apps.market.services import fundamentals as fundamentals_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metric_response(
    pe=28.5,
    eps=6.42,
    gross_margin=43.5,
    net_margin=25.3,
    rev_growth=8.1,
    market_cap=2800000.0,
    beta=1.23,
    div_yield=0.51,
    wk52_high=199.0,
    wk52_low=142.0,
):
    return {
        "metric": {
            "peTTM": pe,
            "epsBasicExclExtraTTM": eps,
            "grossMarginTTM": gross_margin,
            "netProfitMarginTTM": net_margin,
            "revenueGrowthTTMYoy": rev_growth,
            "marketCapitalization": market_cap,
            "beta": beta,
            "dividendYieldIndicatedAnnual": div_yield,
            "52WeekHigh": wk52_high,
            "52WeekLow": wk52_low,
        }
    }


def _make_profile_response(sector="Technology", industry="Consumer Electronics", name="Apple Inc."):
    return {
        "finnhubIndustry": industry,
        "name": name,
    }


# ---------------------------------------------------------------------------
# Tests: normalized dict values from mocked Finnhub responses
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_fundamentals_returns_normalized_dict():
    metric_body = _make_metric_response()
    profile_body = _make_profile_response()

    def _fake_finnhub_get(path, params, api_key):
        if "metric" in path:
            return metric_body
        return profile_body

    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="testkey"),
        patch("apps.market.services.fundamentals._finnhub_get", side_effect=_fake_finnhub_get),
        patch(
            "apps.market.services.fundamentals.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fundamentals_mod.fetch_fundamentals("AAPL")

    assert result["ticker"] == "AAPL"
    assert result["pe"] == 28.5
    assert result["eps_ttm"] == 6.42
    assert result["gross_margin"] == 43.5
    assert result["net_margin"] == 25.3
    assert result["rev_growth_yoy"] == 8.1
    assert result["market_cap"] == 2800000.0
    assert result["beta"] == 1.23
    assert result["div_yield"] == 0.51
    assert result["wk52_high"] == 199.0
    assert result["wk52_low"] == 142.0
    assert result["industry"] == "Consumer Electronics"
    assert "fetched_at" in result


@pytest.mark.django_db
def test_fetch_fundamentals_upserts_company_fundamentals_row():
    metric_body = _make_metric_response()
    profile_body = _make_profile_response(sector="Technology", industry="Consumer Electronics")

    def _fake_get(path, params, api_key):
        if "metric" in path:
            return metric_body
        return profile_body

    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get", side_effect=_fake_get),
        patch(
            "apps.market.services.fundamentals.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        fundamentals_mod.fetch_fundamentals("AAPL")
        fundamentals_mod.fetch_fundamentals("AAPL")  # second call: upserts in place

    assert CompanyFundamentals.objects.filter(ticker="AAPL").count() == 1
    obj = CompanyFundamentals.objects.get(ticker="AAPL")
    assert obj.industry == "Consumer Electronics"
    assert obj.metrics["pe"] == 28.5


@pytest.mark.django_db
def test_fetch_fundamentals_mock_mode_returns_canned_dict():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fundamentals_mod.fetch_fundamentals("ANYTHING")

    assert isinstance(result, dict)
    assert result.get("ticker") is not None
    # canned dict has a real PE value
    assert result.get("pe") is not None
    assert isinstance(result["pe"], int | float)


@pytest.mark.django_db
def test_fetch_fundamentals_never_raises_on_network_failure():
    def _boom(path, params, api_key):
        raise RuntimeError("connection refused")

    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get", side_effect=_boom),
        patch(
            "apps.market.services.fundamentals.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fundamentals_mod.fetch_fundamentals("BOOM")

    assert result == {}


@pytest.mark.django_db
def test_fetch_fundamentals_no_credential_returns_empty():
    with patch("apps.market.services.fundamentals._finnhub_api_key", return_value=None):
        result = fundamentals_mod.fetch_fundamentals("AAPL")

    assert result == {}


@pytest.mark.django_db
def test_fetch_fundamentals_handles_missing_fields_gracefully():
    """If Finnhub returns partial data, None values are filled in."""
    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get", return_value={}),
        patch(
            "apps.market.services.fundamentals.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = fundamentals_mod.fetch_fundamentals("AAPL")

    # Should return a dict (even if empty due to no metric/profile data)
    assert isinstance(result, dict)
