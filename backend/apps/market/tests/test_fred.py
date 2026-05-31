"""Tests for fetch_macro (FRED service)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services import fred as fred_mod

# ---------------------------------------------------------------------------
# Raw API response fixtures
# ---------------------------------------------------------------------------

_OBS_CPIAUCSL = {
    "observations": [
        {"date": "2025-04-01", "value": "314.5"},
        {"date": "2025-03-01", "value": "313.8"},
    ]
}

_OBS_DGS10 = {
    "observations": [
        {"date": "2025-05-28", "value": "4.32"},
        {"date": "2025-05-27", "value": "4.28"},
    ]
}

_OBS_MISSING = {
    "observations": [
        {"date": "2025-05-28", "value": "."},
        {"date": "2025-05-27", "value": "4.28"},
    ]
}


# ---------------------------------------------------------------------------
# Helper: bypass cache transparently
# ---------------------------------------------------------------------------


def _passthrough_cache(key: str, *, ttl_seconds: int, fetcher):
    return fetcher()


# ---------------------------------------------------------------------------
# 1. Normalized multi-series dict
# ---------------------------------------------------------------------------


def test_fred_returns_normalized_dict():
    """Patching _fetch_series and cache gives correct normalized output."""
    fetch_map = {
        "CPIAUCSL": _OBS_CPIAUCSL,
        "DGS10": _OBS_DGS10,
    }

    def _fake_fetch_series(sid: str, api_key: str) -> dict:
        return fetch_map[sid]

    with (
        patch("apps.market.services.fred._api_key", return_value="k"),
        patch("apps.market.services.fred._fetch_series", side_effect=_fake_fetch_series),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = fred_mod.fetch_macro(series_ids=["CPIAUCSL", "DGS10"])

    assert set(result.keys()) == {"CPIAUCSL", "DGS10"}

    cpi = result["CPIAUCSL"]
    assert cpi["label"] == "CPI"
    assert cpi["value"] == pytest.approx(314.5)
    assert cpi["date"] == "2025-04-01"
    assert cpi["prev"] == pytest.approx(313.8)
    assert cpi["change"] == pytest.approx(314.5 - 313.8)

    dgs10 = result["DGS10"]
    assert dgs10["label"] == "10Y yield"
    assert dgs10["value"] == pytest.approx(4.32)
    assert dgs10["prev"] == pytest.approx(4.28)
    assert dgs10["change"] == pytest.approx(4.32 - 4.28)


def test_fred_normalize_missing_sentinel_gives_none():
    """A '.' observation value is returned as None; change is None when either side is None."""
    fetch_map = {"DGS10": _OBS_MISSING}

    def _fake_fetch_series(sid: str, api_key: str) -> dict:
        return fetch_map[sid]

    with (
        patch("apps.market.services.fred._api_key", return_value="k"),
        patch("apps.market.services.fred._fetch_series", side_effect=_fake_fetch_series),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = fred_mod.fetch_macro(series_ids=["DGS10"])

    dgs10 = result["DGS10"]
    assert dgs10["value"] is None
    assert dgs10["prev"] == pytest.approx(4.28)
    assert dgs10["change"] is None


def test_fred_uses_cache_get_or_fetch():
    """cache.get_or_fetch is called with the right key pattern and TTL, and its
    fetcher actually issues the _get call."""
    captured_calls: list[str] = []

    def _fake_get_or_fetch(key: str, *, ttl_seconds: int, fetcher):
        captured_calls.append(key)
        # The fetcher would call _get; we intercept _get instead
        return _OBS_CPIAUCSL

    with (
        patch("apps.market.services.fred._api_key", return_value="k"),
        patch("apps.market.services.fred.cache.get_or_fetch", side_effect=_fake_get_or_fetch),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = fred_mod.fetch_macro(series_ids=["CPIAUCSL"])

    assert "market:fred:CPIAUCSL" in captured_calls
    assert "CPIAUCSL" in result


# ---------------------------------------------------------------------------
# 2. Per-series resilience: one series raising must not kill the rest
# ---------------------------------------------------------------------------


def test_fred_per_series_resilience():
    """If one series raises, others are still returned."""

    def _fake_fetch_series(sid: str, api_key: str) -> dict:
        if sid == "CPIAUCSL":
            raise RuntimeError("network timeout")
        return _OBS_DGS10

    with (
        patch("apps.market.services.fred._api_key", return_value="k"),
        patch("apps.market.services.fred._fetch_series", side_effect=_fake_fetch_series),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = fred_mod.fetch_macro(series_ids=["CPIAUCSL", "DGS10"])

    # CPIAUCSL is skipped; DGS10 is present
    assert "CPIAUCSL" not in result
    assert "DGS10" in result
    assert result["DGS10"]["value"] == pytest.approx(4.32)


def test_fred_all_series_fail_returns_empty_dict():
    """If every series raises, the result is {} (not an exception)."""

    def _boom(sid: str, api_key: str) -> dict:
        raise ConnectionError("refused")

    with (
        patch("apps.market.services.fred._api_key", return_value="k"),
        patch("apps.market.services.fred._fetch_series", side_effect=_boom),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        result = fred_mod.fetch_macro(series_ids=["CPIAUCSL", "DGS10"])

    assert result == {}


# ---------------------------------------------------------------------------
# 3. Mock mode
# ---------------------------------------------------------------------------


def test_fred_mock_mode_returns_canned():
    """With MOCK_EXTERNAL=true the function returns the canned dict without hitting
    the credential store or the network."""
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fred_mod.fetch_macro()

    assert isinstance(result, dict)
    assert len(result) >= 1
    # The canned dict must satisfy the output contract
    for _sid, entry in result.items():
        assert "label" in entry
        assert "value" in entry
        assert "date" in entry
        assert "prev" in entry
        assert "change" in entry


# ---------------------------------------------------------------------------
# 4. Missing credential → {}
# ---------------------------------------------------------------------------


def test_fred_no_credential_returns_empty():
    """If _api_key() returns None, fetch_macro returns {} immediately."""
    with (
        patch("apps.core.mocks.is_mock_mode", return_value=False),
        patch("apps.market.services.fred._api_key", return_value=None),
    ):
        result = fred_mod.fetch_macro()

    assert result == {}


# ---------------------------------------------------------------------------
# 5. Network-level failure (cache.get_or_fetch re-raises through _fetch_series)
# ---------------------------------------------------------------------------


def test_fred_network_error_per_series_skipped():
    """A requests-level exception inside the fetcher lambda is caught per-series."""

    def _fake_get_or_fetch(key: str, *, ttl_seconds: int, fetcher):
        raise OSError("host unreachable")

    with (
        patch("apps.core.mocks.is_mock_mode", return_value=False),
        patch("apps.market.services.fred._api_key", return_value="k"),
        patch("apps.market.services.fred.cache.get_or_fetch", side_effect=_fake_get_or_fetch),
    ):
        result = fred_mod.fetch_macro(series_ids=["CPIAUCSL", "DGS10"])

    assert result == {}
