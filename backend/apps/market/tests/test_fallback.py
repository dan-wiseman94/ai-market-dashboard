"""Free-provider fallback used when Schwab isn't connected."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.services import fallback
from apps.secrets.models import ApiCredential

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}


def _cred(provider: str) -> None:
    ApiCredential.objects.create(provider=provider, token={"api_key": "k", "api_secret": "s"})


# --- alt_quotes -------------------------------------------------------------


@pytest.mark.django_db
def test_alt_quotes_none_when_no_provider():
    assert fallback.alt_quotes(["AAPL"]) is None


@pytest.mark.django_db
def test_alt_quotes_prefers_alpaca_over_twelvedata():
    _cred("alpaca")
    _cred("twelvedata")
    with patch(
        "apps.market.services.alpaca.fetch_quotes", return_value={"AAPL": {"last": 1.0}}
    ) as m:
        assert fallback.alt_quotes(["AAPL"]) == {"AAPL": {"last": 1.0}}
    m.assert_called_once()


@pytest.mark.django_db
def test_alt_quotes_falls_to_twelvedata():
    _cred("twelvedata")
    with patch(
        "apps.market.services.twelvedata.fetch_quotes", return_value={"AAPL": {"last": 2.0}}
    ):
        assert fallback.alt_quotes(["AAPL"]) == {"AAPL": {"last": 2.0}}


# --- alt_bars ---------------------------------------------------------------


@pytest.mark.django_db
def test_alt_bars_none_when_no_provider():
    assert fallback.alt_bars("AAPL", "1d") is None


@pytest.mark.django_db
def test_alt_bars_alpaca_serves_any_timeframe():
    _cred("alpaca")
    with patch("apps.market.services.alpaca.fetch_bars", return_value=[{"close": 1}]) as m:
        assert fallback.alt_bars("AAPL", "5m", limit=10) == [{"close": 1}]
    m.assert_called_once_with("AAPL", timeframe="5m", limit=10)


@pytest.mark.django_db
def test_alt_bars_twelvedata_maps_our_timeframe_to_interval():
    _cred("twelvedata")
    with patch(
        "apps.market.services.twelvedata.fetch_time_series", return_value=[{"close": 2}]
    ) as m:
        fallback.alt_bars("AAPL", "15m", limit=10)
    m.assert_called_once_with("AAPL", interval="15min", outputsize=10)


@pytest.mark.django_db
def test_alt_bars_tiingo_is_daily_only():
    _cred("tiingo")
    with patch("apps.market.services.tiingo.fetch_daily_bars", return_value=[{"close": 3}]):
        assert fallback.alt_bars("AAPL", "1d", limit=30) == [{"close": 3}]
    # An intraday request is not served by a daily-only provider.
    assert fallback.alt_bars("AAPL", "5m") is None


@pytest.mark.django_db
def test_alt_bars_polygon_is_daily_only():
    _cred("polygon")
    with patch("apps.market.services.polygon.fetch_daily_bars", return_value=[{"close": 4}]):
        assert fallback.alt_bars("AAPL", "1d") == [{"close": 4}]
    assert fallback.alt_bars("AAPL", "1m") is None


# --- alt_chain / alt_news ---------------------------------------------------


@pytest.mark.django_db
def test_alt_chain_none_without_tradier():
    assert fallback.alt_chain("AAPL") is None


@pytest.mark.django_db
def test_alt_chain_uses_tradier():
    _cred("tradier")
    chain = {"ticker": "AAPL", "underlying_last": None, "expiries": {}}
    with patch("apps.market.services.tradier.fetch_chain", return_value=chain):
        assert fallback.alt_chain("AAPL")["ticker"] == "AAPL"


@pytest.mark.django_db
def test_alt_news_none_without_provider():
    assert fallback.alt_news(["AAPL"]) is None


@pytest.mark.django_db
def test_alt_news_prefers_marketaux_over_tiingo():
    _cred("marketaux")
    _cred("tiingo")
    with patch("apps.market.services.marketaux.fetch_news", return_value=[{"headline": "x"}]) as m:
        assert fallback.alt_news(["AAPL"]) == [{"headline": "x"}]
    m.assert_called_once()


# --- service-level integration ---------------------------------------------


@pytest.mark.django_db
def test_fetch_quotes_falls_back_when_schwab_absent():
    from apps.market.services import quotes

    _cred("alpaca")
    with (
        patch(
            "apps.market.services.quotes.get_schwab_client",
            side_effect=SchwabNotConnectedError("no"),
        ),
        patch("apps.market.services.alpaca.fetch_quotes", return_value={"AAPL": {"last": 9.0}}),
        patch("apps.market.services.quotes.cache.get_or_fetch", **_PASSTHRU),
    ):
        assert quotes.fetch_quotes(["AAPL"]) == {"AAPL": {"last": 9.0}}


@pytest.mark.django_db
def test_fetch_quotes_reraises_when_no_alt_provider():
    from apps.market.services import quotes

    with (
        patch(
            "apps.market.services.quotes.get_schwab_client",
            side_effect=SchwabNotConnectedError("no"),
        ),
        patch("apps.market.services.quotes.cache.get_or_fetch", **_PASSTHRU),
        pytest.raises(SchwabNotConnectedError),
    ):
        quotes.fetch_quotes(["AAPL"])


# --- .env-backed keys count as configured ------------------------------------------


@pytest.mark.django_db
def test_alt_quotes_uses_env_configured_provider(settings):
    """No ApiCredential row at all — a DATA_SOURCE_ENV_KEYS key alone must route the
    fallback (DB rows die with `docker compose down -v`; .env keys survive)."""
    settings.DATA_SOURCE_ENV_KEYS = {"alpaca": {"api_key": "env-k", "api_secret": "env-s"}}
    with patch(
        "apps.market.services.alpaca.fetch_quotes", return_value={"AAPL": {"last": 7.0}}
    ) as m:
        assert fallback.alt_quotes(["AAPL"]) == {"AAPL": {"last": 7.0}}
    m.assert_called_once()
