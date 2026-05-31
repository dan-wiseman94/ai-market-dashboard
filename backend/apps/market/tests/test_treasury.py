"""Tests for the US Treasury FiscalData service (treasury.py).

No Django DB required — the service has no model upserts.
All external I/O is patched; no real network calls are made.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services import treasury as treasury_mod

# ---------------------------------------------------------------------------
# Raw API response fixtures
# ---------------------------------------------------------------------------

_RAW_RATES_RESPONSE = {
    "data": [
        {
            "record_date": "2025-04-30",
            "security_type_desc": "Marketable",
            "security_desc": "Treasury Bills",
            "avg_interest_rate_amt": "4.320000",
        },
        {
            "record_date": "2025-04-30",
            "security_type_desc": "Marketable",
            "security_desc": "Treasury Notes",
            "avg_interest_rate_amt": "4.150000",
        },
        # Older row — must be excluded (not the latest date)
        {
            "record_date": "2025-03-31",
            "security_type_desc": "Marketable",
            "security_desc": "Treasury Bills",
            "avg_interest_rate_amt": "4.100000",
        },
    ],
    "meta": {"count": 3, "total-count": 3},
}

_RAW_DEBT_RESPONSE = {
    "data": [
        {
            "record_date": "2025-05-29",
            "tot_pub_debt_out_amt": "36200000000000.00",
        }
    ],
    "meta": {"count": 1, "total-count": 1},
}


# ---------------------------------------------------------------------------
# Helper: make cache.get_or_fetch call through to fetcher()
# ---------------------------------------------------------------------------

_PASSTHROUGH_CACHE = lambda key, *, ttl_seconds, fetcher: fetcher()  # noqa: E731


# ---------------------------------------------------------------------------
# fetch_treasury_rates
# ---------------------------------------------------------------------------


def test_fetch_treasury_rates_normalized_latest_only():
    """Only rows from the latest record_date are included in the rates dict."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch(
            "apps.market.services.treasury._get",
            return_value=_RAW_RATES_RESPONSE,
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury_rates()

    assert result["record_date"] == "2025-04-30"
    rates = result["rates"]
    # Only the two 2025-04-30 rows should be present
    assert set(rates.keys()) == {"Treasury Bills", "Treasury Notes"}
    assert rates["Treasury Bills"] == pytest.approx(4.32)
    assert rates["Treasury Notes"] == pytest.approx(4.15)
    # Older (2025-03-31) row must not bleed through
    assert len(rates) == 2


def test_fetch_treasury_rates_float_coercion():
    """avg_interest_rate_amt strings are coerced to float."""
    raw = {
        "data": [
            {
                "record_date": "2025-04-30",
                "security_type_desc": "Marketable",
                "security_desc": "Treasury Bonds",
                "avg_interest_rate_amt": "4.550000",
            }
        ],
        "meta": {},
    }
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.market.services.treasury._get", return_value=raw),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury_rates()

    assert isinstance(result["rates"]["Treasury Bonds"], float)
    assert result["rates"]["Treasury Bonds"] == pytest.approx(4.55)


def test_fetch_treasury_rates_bad_float_skipped():
    """Rows with an unparseable rate string are skipped, others still returned."""
    raw = {
        "data": [
            {
                "record_date": "2025-04-30",
                "security_type_desc": "Marketable",
                "security_desc": "Good",
                "avg_interest_rate_amt": "3.75",
            },
            {
                "record_date": "2025-04-30",
                "security_type_desc": "Marketable",
                "security_desc": "Bad",
                "avg_interest_rate_amt": "N/A",
            },
        ],
        "meta": {},
    }
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.market.services.treasury._get", return_value=raw),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury_rates()

    assert "Good" in result["rates"]
    assert "Bad" not in result["rates"]


def test_fetch_treasury_rates_empty_data_returns_empty():
    """Empty data array → {}."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.market.services.treasury._get", return_value={"data": [], "meta": {}}),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury_rates()

    assert result == {}


def test_fetch_treasury_rates_mock_mode():
    """Mock mode returns the canned rates fixture without any network call."""
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = treasury_mod.fetch_treasury_rates()

    assert isinstance(result, dict)
    assert "record_date" in result
    assert "rates" in result
    assert isinstance(result["rates"], dict)
    assert len(result["rates"]) > 0


def test_fetch_treasury_rates_never_raises_on_network_failure():
    """A network error in _get must NOT propagate; {} is returned instead."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch(
            "apps.market.services.treasury._get",
            side_effect=RuntimeError("connection refused"),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury_rates()

    assert result == {}


def test_fetch_treasury_rates_never_raises_on_cache_failure():
    """A cache failure (e.g. Redis down) must NOT propagate; {} is returned instead."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=OSError("redis gone"),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury_rates()

    assert result == {}


# ---------------------------------------------------------------------------
# fetch_debt_to_penny
# ---------------------------------------------------------------------------


def test_fetch_debt_to_penny_normalized():
    """Debt amount is coerced to float and record_date is returned."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.market.services.treasury._get", return_value=_RAW_DEBT_RESPONSE),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_debt_to_penny()

    assert result["record_date"] == "2025-05-29"
    assert isinstance(result["total_public_debt"], float)
    assert result["total_public_debt"] == pytest.approx(36_200_000_000_000.0)


def test_fetch_debt_to_penny_empty_data_returns_empty():
    """Empty data array → {}."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.market.services.treasury._get", return_value={"data": [], "meta": {}}),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_debt_to_penny()

    assert result == {}


def test_fetch_debt_to_penny_bad_float_returns_empty():
    """An unparseable tot_pub_debt_out_amt returns {}."""
    raw = {
        "data": [{"record_date": "2025-05-29", "tot_pub_debt_out_amt": "not-a-number"}],
        "meta": {},
    }
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.market.services.treasury._get", return_value=raw),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_debt_to_penny()

    assert result == {}


def test_fetch_debt_to_penny_mock_mode():
    """Mock mode returns the canned debt fixture without any network call."""
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = treasury_mod.fetch_debt_to_penny()

    assert isinstance(result, dict)
    assert "record_date" in result
    assert "total_public_debt" in result
    assert isinstance(result["total_public_debt"], float)
    assert result["total_public_debt"] > 0


def test_fetch_debt_to_penny_never_raises_on_network_failure():
    """A network error must NOT propagate; {} is returned instead."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch(
            "apps.market.services.treasury._get",
            side_effect=ConnectionError("timeout"),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_debt_to_penny()

    assert result == {}


def test_fetch_debt_to_penny_never_raises_on_cache_failure():
    """A cache failure must NOT propagate; {} is returned instead."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=OSError("redis gone"),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_debt_to_penny()

    assert result == {}


# ---------------------------------------------------------------------------
# fetch_treasury (combined)
# ---------------------------------------------------------------------------


def test_fetch_treasury_combined_shape():
    """fetch_treasury returns {"rates": {...}, "debt": {...}} from both sub-fetches."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch(
            "apps.market.services.treasury._get",
            side_effect=lambda path, params: (
                _RAW_RATES_RESPONSE if "avg_interest_rates" in path else _RAW_DEBT_RESPONSE
            ),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury()

    assert set(result.keys()) == {"rates", "debt"}
    assert result["rates"]["record_date"] == "2025-04-30"
    assert result["debt"]["record_date"] == "2025-05-29"


def test_fetch_treasury_rates_failure_does_not_kill_debt():
    """If fetch_treasury_rates returns {}, fetch_treasury still returns debt."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch(
            "apps.market.services.treasury._get",
            side_effect=lambda path, params: (
                (_ for _ in ()).throw(RuntimeError("rates down"))
                if "avg_interest_rates" in path
                else _RAW_DEBT_RESPONSE
            ),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury()

    assert result["rates"] == {}
    assert result["debt"]["record_date"] == "2025-05-29"


def test_fetch_treasury_debt_failure_does_not_kill_rates():
    """If fetch_debt_to_penny returns {}, fetch_treasury still returns rates."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch(
            "apps.market.services.treasury._get",
            side_effect=lambda path, params: (
                _RAW_RATES_RESPONSE
                if "avg_interest_rates" in path
                else (_ for _ in ()).throw(RuntimeError("debt down"))
            ),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury()

    assert result["debt"] == {}
    assert result["rates"]["record_date"] == "2025-04-30"


def test_fetch_treasury_mock_mode():
    """Mock mode short-circuits both sub-fetches; combined result is well-formed."""
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = treasury_mod.fetch_treasury()

    assert "rates" in result
    assert "debt" in result
    assert "record_date" in result["rates"]
    assert "rates" in result["rates"]
    assert "record_date" in result["debt"]
    assert "total_public_debt" in result["debt"]


def test_fetch_treasury_both_fail_returns_empty_dicts():
    """If both sub-fetches fail, the combined result has empty dicts (never raises)."""
    with (
        patch(
            "apps.market.services.treasury.cache.get_or_fetch",
            side_effect=OSError("redis gone"),
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = treasury_mod.fetch_treasury()

    assert result == {"rates": {}, "debt": {}}
