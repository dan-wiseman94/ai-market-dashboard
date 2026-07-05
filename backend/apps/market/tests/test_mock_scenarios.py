"""Service error-injection scenarios are honored by the market mock clients.

These exercise the wiring that turns a ``(scenario, service)`` mapping in
``apps.core.mocks.scenarios`` into real behavior — a dispatch no client
consumes would leave the scenarios silently inert.
"""

from unittest.mock import patch

import pytest

from apps.core.mocks import reset_scenario, set_scenario


def test_fetch_news_raises_under_news_503():
    from apps.market.services.news import fetch_news

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        set_scenario("news-503")
        try:
            with pytest.raises(RuntimeError, match="503"):
                fetch_news(["AAPL"])
        finally:
            reset_scenario()


def test_fetch_news_returns_canned_under_default():
    from apps.market.services.news import fetch_news

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        reset_scenario()
        items = fetch_news(["AAPL"])
    assert isinstance(items, list)


def test_mock_schwab_client_raises_under_schwab_401():
    from apps.market.schwab_client import _MockSchwabClient

    set_scenario("schwab-401")
    try:
        with pytest.raises(RuntimeError, match="401"):
            _MockSchwabClient().get_quotes(["AAPL"])
    finally:
        reset_scenario()


def test_mock_schwab_client_ok_under_default():
    from apps.market.schwab_client import _MockSchwabClient

    reset_scenario()
    resp = _MockSchwabClient().get_quotes(["AAPL"])
    assert "AAPL" in resp.json()


def test_mock_schwab_client_ohlc_fallthrough_honors_scenario():
    """The __getattr__ OHLC fallback also gates on the scenario."""
    from apps.market.schwab_client import _MockSchwabClient

    set_scenario("schwab-401")
    try:
        with pytest.raises(RuntimeError, match="401"):
            _MockSchwabClient().get_price_history_every_minute("AAPL")
    finally:
        reset_scenario()


def test_fetch_earnings_raises_under_news_503():
    from apps.market.services.events import fetch_earnings

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        set_scenario("news-503")
        try:
            with pytest.raises(RuntimeError, match="503"):
                fetch_earnings(["AAPL"])
        finally:
            reset_scenario()


def test_fetch_macro_raises_under_news_503():
    from apps.market.services.events import fetch_macro

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        set_scenario("news-503")
        try:
            with pytest.raises(RuntimeError, match="503"):
                fetch_macro()
        finally:
            reset_scenario()
