from unittest.mock import patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.context import CONTEXT_SYMBOLS, SECTOR_ETFS, fetch_market_context


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)


def test_context_symbols_includes_core_and_sectors():
    assert "SPY" in CONTEXT_SYMBOLS
    assert "QQQ" in CONTEXT_SYMBOLS
    assert "$VIX" in CONTEXT_SYMBOLS
    for etf in SECTOR_ETFS:
        assert etf in CONTEXT_SYMBOLS


@pytest.mark.django_db
def test_fetch_market_context_shape():
    quotes = {s: {"last": 100.0 + i} for i, s in enumerate(CONTEXT_SYMBOLS)}
    with patch("apps.market.services.context.fetch_quotes", return_value=quotes):
        ctx = fetch_market_context()
    assert ctx["spy_last"] == quotes["SPY"]["last"]
    assert ctx["qqq_last"] == quotes["QQQ"]["last"]
    assert ctx["vix_last"] == quotes["$VIX"]["last"]
    for etf in SECTOR_ETFS:
        assert etf in ctx["sectors"]
    assert "breadth" in ctx  # may be empty dict, that's fine
