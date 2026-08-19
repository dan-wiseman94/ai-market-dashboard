"""Tests for the Tradier option chain service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.models import OptionChainSnapshot
from apps.market.services import tradier as tradier_mod

EXPIRATIONS_RESPONSE = {"expirations": {"date": ["2026-01-16", "2026-02-20"]}}

EXPIRATIONS_SINGLE_DATE_RESPONSE = {
    "expirations": {
        "date": "2026-01-16"  # single string, not a list
    }
}

CHAIN_RESPONSE_2026_01_16 = {
    "options": {
        "option": [
            {
                "strike": 145.0,
                "option_type": "call",
                "bid": 6.2,
                "ask": 6.4,
                "last": 6.3,
                "volume": 500,
                "open_interest": 2000,
                "greeks": {
                    "delta": 0.65,
                    "gamma": 0.04,
                    "theta": -0.05,
                    "vega": 0.12,
                    "mid_iv": 0.28,
                },
            },
            {
                "strike": 145.0,
                "option_type": "put",
                "bid": 1.1,
                "ask": 1.2,
                "last": 1.15,
                "volume": 300,
                "open_interest": 1500,
                "greeks": {
                    "delta": -0.35,
                    "gamma": 0.04,
                    "theta": -0.05,
                    "vega": 0.12,
                    "mid_iv": 0.28,
                },
            },
            {
                "strike": 150.0,
                "option_type": "call",
                "bid": 3.1,
                "ask": 3.2,
                "last": 3.15,
                "volume": 800,
                "open_interest": 4000,
                "greeks": {
                    "delta": 0.50,
                    "gamma": 0.05,
                    "theta": -0.06,
                    "vega": 0.15,
                    "mid_iv": 0.30,
                },
            },
        ]
    }
}

CHAIN_RESPONSE_2026_02_20 = {
    "options": {
        "option": [
            {
                "strike": 150.0,
                "option_type": "call",
                "bid": 4.5,
                "ask": 4.7,
                "last": 4.6,
                "volume": 200,
                "open_interest": 1000,
                "greeks": {
                    "delta": 0.52,
                    "gamma": 0.03,
                    "theta": -0.03,
                    "vega": 0.20,
                    "mid_iv": 0.32,
                },
            }
        ]
    }
}

QUOTE_RESPONSE = {
    "quotes": {
        "quote": {
            "symbol": "AAPL",
            "last": 150.75,
        }
    }
}


def _fake_get_factory(ticker: str = "AAPL"):
    """Return a side_effect function that dispatches on path."""

    def _fake_get(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return EXPIRATIONS_RESPONSE
        if "quotes" in path:
            return QUOTE_RESPONSE
        expiry = params.get("expiration", "")
        if expiry == "2026-01-16":
            return CHAIN_RESPONSE_2026_01_16
        if expiry == "2026-02-20":
            return CHAIN_RESPONSE_2026_02_20
        return {}

    return _fake_get


@pytest.mark.django_db
def test_fetch_chain_returns_normalized_chain():
    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_factory()),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=2)

    assert result["ticker"] == "AAPL"
    assert result["underlying_last"] == "150.75"
    assert "2026-01-16" in result["expiries"]
    assert "2026-02-20" in result["expiries"]


@pytest.mark.django_db
def test_fetch_chain_calls_puts_split_correctly():
    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_factory()),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=2)

    exp = result["expiries"]["2026-01-16"]
    assert all(c["delta"] is not None for c in exp["calls"])
    assert len(exp["calls"]) == 2  # 145 + 150 calls
    assert len(exp["puts"]) == 1  # 145 put only


@pytest.mark.django_db
def test_fetch_chain_strike_sorted_ascending():
    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_factory()),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    calls = result["expiries"]["2026-01-16"]["calls"]
    strikes = [float(c["strike"]) for c in calls]
    assert strikes == sorted(strikes)


@pytest.mark.django_db
def test_fetch_chain_2dp_string_formatting():
    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_factory()),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    call = result["expiries"]["2026-01-16"]["calls"][0]
    for field in ("strike", "bid", "ask", "last", "delta", "gamma", "theta", "vega", "iv"):
        val = call[field]
        assert isinstance(val, str), f"{field} must be a string, got {type(val)}"
        assert "." in val and len(val.split(".")[1]) == 2, f"{field}={val!r} not 2dp"
    assert isinstance(call["volume"], int)
    assert isinstance(call["oi"], int)


@pytest.mark.django_db
def test_fetch_chain_persists_option_chain_snapshot():
    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_factory()),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        tradier_mod.fetch_chain("AAPL", max_expiries=2)
        tradier_mod.fetch_chain("AAPL", max_expiries=2)  # second call creates another row

    rows = OptionChainSnapshot.objects.filter(ticker="AAPL")
    assert rows.count() == 2  # each non-cached call creates a new snapshot row
    first = rows.order_by("fetched_at").first()
    assert "2026-01-16" in first.expiries
    assert "2026-02-20" in first.expiries
    assert first.payload["ticker"] == "AAPL"
    assert first.payload["underlying_last"] == "150.75"


@pytest.mark.django_db
def test_fetch_chain_single_expiration_string_normalised():
    def _fake_get_single(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return EXPIRATIONS_SINGLE_DATE_RESPONSE
        if "quotes" in path:
            return QUOTE_RESPONSE
        return CHAIN_RESPONSE_2026_01_16

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_single),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=2)

    assert "2026-01-16" in result["expiries"]
    assert len(result["expiries"]) == 1


@pytest.mark.django_db
def test_fetch_chain_single_option_dict_normalised():
    single_option_response = {
        "options": {
            "option": {  # dict, not list
                "strike": 145.0,
                "option_type": "call",
                "bid": 6.2,
                "ask": 6.4,
                "last": 6.3,
                "volume": 500,
                "open_interest": 2000,
                "greeks": {
                    "delta": 0.65,
                    "gamma": 0.04,
                    "theta": -0.05,
                    "vega": 0.12,
                    "mid_iv": 0.28,
                },
            }
        }
    }

    def _fake_get_single_opt(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return EXPIRATIONS_SINGLE_DATE_RESPONSE
        if "quotes" in path:
            return QUOTE_RESPONSE
        return single_option_response

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_single_opt),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    calls = result["expiries"]["2026-01-16"]["calls"]
    assert len(calls) == 1
    assert calls[0]["strike"] == "145.00"


@pytest.mark.django_db
def test_fetch_chain_null_greeks_emits_none_fields():
    null_greeks_response = {
        "options": {
            "option": [
                {
                    "strike": 145.0,
                    "option_type": "call",
                    "bid": 2.0,
                    "ask": 2.1,
                    "last": 2.05,
                    "volume": 100,
                    "open_interest": 500,
                    "greeks": None,
                }
            ]
        }
    }

    def _fake_get_null(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return EXPIRATIONS_SINGLE_DATE_RESPONSE
        if "quotes" in path:
            return QUOTE_RESPONSE
        return null_greeks_response

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_null),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    call = result["expiries"]["2026-01-16"]["calls"][0]
    for field in ("delta", "gamma", "theta", "vega", "iv"):
        assert call[field] is None, f"{field} should be None when greeks is null"


@pytest.mark.django_db
def test_fetch_chain_iv_falls_back_to_smv_vol():
    smv_vol_response = {
        "options": {
            "option": [
                {
                    "strike": 145.0,
                    "option_type": "call",
                    "bid": 2.0,
                    "ask": 2.1,
                    "last": 2.05,
                    "volume": 100,
                    "open_interest": 500,
                    "greeks": {
                        "delta": 0.5,
                        "gamma": 0.03,
                        "theta": -0.04,
                        "vega": 0.10,
                        "mid_iv": None,
                        "smv_vol": 0.35,
                    },
                }
            ]
        }
    }

    def _fake_get_smv(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return EXPIRATIONS_SINGLE_DATE_RESPONSE
        if "quotes" in path:
            return QUOTE_RESPONSE
        return smv_vol_response

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_smv),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    call = result["expiries"]["2026-01-16"]["calls"][0]
    assert call["iv"] == "0.35"


@pytest.mark.django_db
def test_fetch_chain_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = tradier_mod.fetch_chain("AAPL")

    assert isinstance(result, dict)
    assert result["ticker"] == "AAPL"
    assert isinstance(result["underlying_last"], str)
    assert isinstance(result["expiries"], dict)
    assert len(result["expiries"]) >= 1
    first_exp = next(iter(result["expiries"].values()))
    assert len(first_exp["calls"]) >= 1
    assert len(first_exp["puts"]) >= 1


@pytest.mark.django_db
def test_fetch_chain_no_credential_returns_empty():
    with patch("apps.market.services.tradier._api_key", return_value=None):
        result = tradier_mod.fetch_chain("AAPL")

    assert result == {"ticker": "AAPL", "underlying_last": None, "expiries": {}}


@pytest.mark.django_db
def test_fetch_chain_never_raises_on_network_failure():
    def _boom(path: str, params: dict, *, api_key: str):
        raise RuntimeError("connection refused")

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_boom),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL")

    assert result == {"ticker": "AAPL", "underlying_last": None, "expiries": {}}


@pytest.mark.django_db
def test_fetch_chain_max_expiries_respected():
    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_factory()),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    assert len(result["expiries"]) == 1
    assert "2026-01-16" in result["expiries"]
    assert "2026-02-20" not in result["expiries"]


@pytest.mark.django_db
def test_fetch_chain_empty_expirations_returns_empty():
    def _fake_get_no_exp(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return {"expirations": {"date": []}}
        return {}

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_no_exp),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL")

    assert result == {"ticker": "AAPL", "underlying_last": None, "expiries": {}}


@pytest.mark.django_db
def test_fetch_chain_quote_list_takes_matching_symbol():
    multi_quote_response = {
        "quotes": {
            "quote": [
                {"symbol": "SPY", "last": 500.0},
                {"symbol": "AAPL", "last": 175.50},
            ]
        }
    }

    def _fake_get_multi_quote(path: str, params: dict, *, api_key: str) -> dict:
        if "expirations" in path:
            return EXPIRATIONS_SINGLE_DATE_RESPONSE
        if "quotes" in path:
            return multi_quote_response
        return CHAIN_RESPONSE_2026_01_16

    with (
        patch("apps.market.services.tradier._api_key", return_value="testkey"),
        patch("apps.market.services.tradier._get", side_effect=_fake_get_multi_quote),
        patch(
            "apps.market.services.tradier.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        result = tradier_mod.fetch_chain("AAPL", max_expiries=1)

    assert result["underlying_last"] == "175.50"
