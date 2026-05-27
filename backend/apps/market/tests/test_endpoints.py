from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.market import cache as cache_module


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Isolate the market cache per test.

    `apps.market.cache` talks to real Redis via `settings.REDIS_URL` (not
    Django's cache framework), so cache entries persist across tests, across
    runs, and are shared with the running dev stack. Without isolation a
    leftover `market:positions` key makes `fetch_positions` return a cache hit
    and skip `_fetch_from_schwab` entirely — which silently broke
    `test_not_connected_returns_503` whenever that key was warm. Swap `_redis`
    for an empty fakeredis, matching the `test_services_*` convention.
    """
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def no_schwab(monkeypatch):
    """Raise SchwabNotConnectedError from every fetch service."""
    from apps.market.schwab_client import SchwabNotConnectedError

    def boom(*a, **kw):
        raise SchwabNotConnectedError("not connected")

    monkeypatch.setattr("apps.market.services.quotes._fetch_from_schwab", boom)
    monkeypatch.setattr("apps.market.services.ohlc._fetch_from_schwab", boom)
    monkeypatch.setattr("apps.market.services.positions._fetch_from_schwab", boom)


@pytest.mark.django_db
def test_quotes_endpoint_happy(api):
    with patch("apps.market.views.fetch_quotes", return_value={"SPY": {"last": 550.0}}):
        r = api.get("/api/market/quotes/?tickers=SPY")
        assert r.status_code == 200
        assert r.json() == {"SPY": {"last": 550.0}}


@pytest.mark.django_db
def test_quotes_endpoint_missing_param(api):
    r = api.get("/api/market/quotes/")
    assert r.status_code == 400
    assert r.json()["code"] == "missing_tickers"


@pytest.mark.django_db
def test_ohlc_endpoint_happy(api):
    bars = [
        {
            "ts": "2026-01-01T00:00:00+00:00",
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 2,
            "volume": 10,
        }
    ]
    with patch("apps.market.views.fetch_ohlc", return_value=bars):
        r = api.get("/api/market/ohlc/?ticker=SPY&timeframe=1m&bars=60")
        assert r.status_code == 200
        assert r.json()["bars"] == bars


@pytest.mark.django_db
def test_positions_endpoint_happy(api):
    with patch("apps.market.views.fetch_positions", return_value=[{"ticker": "NVDA", "qty": 100}]):
        r = api.get("/api/market/positions/")
        assert r.status_code == 200
        assert r.json()[0]["ticker"] == "NVDA"


@pytest.mark.django_db
def test_context_endpoint_happy(api):
    ctx = {"spx_last": 6000, "qqq_last": 480, "vix_last": 14, "sectors": {}, "breadth": {}}
    with patch("apps.market.views.fetch_market_context", return_value=ctx):
        r = api.get("/api/market/context/")
        assert r.status_code == 200
        assert r.json() == ctx


@pytest.mark.django_db
def test_not_connected_returns_503(api, no_schwab):
    r = api.get("/api/market/positions/")
    assert r.status_code == 503
    assert r.json()["code"] == "schwab_not_connected"
