"""Tests for the RS + sector-rotation wiring in fetch_market_context.

Separate from test_services_context.py so we can seed OHLCBar and patch
fetch_quotes without touching the existing context test fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from apps.market import cache as cache_module
from apps.market.models import OHLCBar
from apps.market.services.context import CONTEXT_SYMBOLS, SECTOR_ETFS, fetch_market_context

BASE = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
DAY = timedelta(days=1)

_FAKE_QUOTES = {s: {"last": 100.0 + i} for i, s in enumerate(CONTEXT_SYMBOLS)}


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)


def _bar(ticker: str, day_offset: int, close: float) -> None:
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        ts=BASE + DAY * day_offset,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
    )


def _nvda_bars() -> None:
    """6 NVDA daily bars: closes 60..110."""
    for i, close in enumerate([60, 70, 80, 90, 100, 110]):
        _bar("NVDA", i, float(close))


def _spx_bars() -> None:
    """6 $SPX daily bars: closes 4500..5000."""
    for i, close in enumerate([4500, 4600, 4700, 4800, 4900, 5000]):
        _bar("$SPX", i, float(close))


@pytest.mark.django_db
def test_cache_key_differs_by_primary_ticker():
    """Two different primaries must NOT share cached results."""
    _nvda_bars()
    _spx_bars()

    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx_nvda = fetch_market_context(tickers=["NVDA"])
        ctx_aapl = fetch_market_context(tickers=["AAPL"])

    # NVDA has bars → RS present; AAPL has no bars → RS None
    assert ctx_nvda.get("relative_strength") is not None
    assert ctx_aapl.get("relative_strength") is None


@pytest.mark.django_db
def test_existing_keys_preserved_with_tickers():
    """All original keys (spx_last, qqq_last, vix_last, sectors, breadth) still present."""
    _nvda_bars()
    _spx_bars()
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context(tickers=["NVDA"])
    for key in ("spx_last", "qqq_last", "vix_last", "sectors", "breadth"):
        assert key in ctx, f"Missing key: {key}"
    for etf in SECTOR_ETFS:
        assert etf in ctx["sectors"]
