"""Tests for the fundamentals snapshot section fetcher and renderer."""

from unittest.mock import patch

import pytest

from apps.snapshots.serializer import _render_fundamentals, _title
from apps.snapshots.services import _FETCHERS


def test_render_fundamentals_emits_markdown_table_with_known_values():
    payload = {
        "AAPL": {
            "ticker": "AAPL",
            "pe": 28.5,
            "eps_ttm": 6.42,
            "rev_growth_yoy": 8.1,
            "net_margin": 25.3,
            "market_cap": 2_800_000.0,
            "wk52_high": 199.0,
            "wk52_low": 142.0,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }
    }
    out = _render_fundamentals(payload)
    assert "## Company fundamentals" in out
    assert "AAPL" in out
    assert "28.50" in out
    assert "6.42" in out
    assert "8.10" in out
    assert "25.30" in out
    assert "Technology" in out


def test_render_fundamentals_handles_missing_fields_with_dash():
    payload = {
        "NVDA": {
            "ticker": "NVDA",
            "pe": None,
            "eps_ttm": None,
            "rev_growth_yoy": None,
            "net_margin": None,
            "market_cap": None,
            "wk52_high": None,
            "wk52_low": None,
            "sector": "",
            "industry": "",
        }
    }
    out = _render_fundamentals(payload)
    assert "NVDA" in out
    assert "—" in out


def test_render_fundamentals_empty_payload():
    out = _render_fundamentals({})
    assert "_(no fundamentals data)_" in out


def test_render_fundamentals_title():
    assert _title("fundamentals") == "Company fundamentals"


def test_render_fundamentals_52wk_position():
    """52wk position column shows where price sits in the annual range."""
    payload = {
        "AAPL": {
            "ticker": "AAPL",
            "pe": 28.5,
            "eps_ttm": 6.42,
            "rev_growth_yoy": 8.1,
            "net_margin": 25.3,
            "market_cap": 2_800_000.0,
            "wk52_high": 200.0,
            "wk52_low": 100.0,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }
    }
    out = _render_fundamentals(payload)
    assert "200" in out or "100" in out


@pytest.mark.django_db
def test_fundamentals_fetcher_returns_data_dict_keyed_by_ticker():
    canned = {
        "ticker": "AAPL",
        "pe": 28.5,
        "eps_ttm": 6.42,
        "gross_margin": 43.5,
        "net_margin": 25.3,
        "rev_growth_yoy": 8.1,
        "market_cap": 2_800_000.0,
        "beta": 1.23,
        "div_yield": 0.51,
        "wk52_high": 199.0,
        "wk52_low": 142.0,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "fetched_at": "2026-05-30T00:00:00+00:00",
    }

    with patch(
        "apps.snapshots.services.fetch_fundamentals",
        side_effect=lambda t: {**canned, "ticker": t},
    ):
        result = _FETCHERS["fundamentals"](watchlist_tickers=["AAPL", "NVDA"])

    assert "data" in result
    assert "AAPL" in result["data"]
    assert "NVDA" in result["data"]
    assert result["data"]["AAPL"]["pe"] == 28.5


@pytest.mark.django_db
def test_fundamentals_fetcher_caps_at_8_tickers():
    tickers = [f"T{i}" for i in range(12)]

    with patch(
        "apps.snapshots.services.fetch_fundamentals",
        return_value={},
    ) as mock_fetch:
        _FETCHERS["fundamentals"](watchlist_tickers=tickers)

    assert mock_fetch.call_count == 8


@pytest.mark.django_db
def test_fundamentals_fetcher_empty_watchlist_returns_empty_data():
    result = _FETCHERS["fundamentals"](watchlist_tickers=[])
    assert result == {"data": {}}
