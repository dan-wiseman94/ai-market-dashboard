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
def test_no_args_returns_expected_shape():
    """fetch_market_context() with no tickers still returns spx/qqq/vix/sectors/breadth."""
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context()
    assert "spx_last" in ctx
    assert "qqq_last" in ctx
    assert "vix_last" in ctx
    assert "sectors" in ctx
    assert "breadth" in ctx


@pytest.mark.django_db
def test_no_args_relative_strength_is_none():
    """With no tickers, relative_strength in the result must be None (no primary)."""
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context()
    assert ctx.get("relative_strength") is None


@pytest.mark.django_db
def test_no_args_sector_rotation_present():
    """sector_rotation key is always present ([] when no bars)."""
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context()
    assert "sector_rotation" in ctx
    assert isinstance(ctx["sector_rotation"], list)


@pytest.mark.django_db
def test_with_tickers_includes_relative_strength():
    """fetch_market_context(tickers=["NVDA"]) includes RS for NVDA."""
    _nvda_bars()
    _spx_bars()
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context(tickers=["NVDA"])
    rs = ctx.get("relative_strength")
    assert rs is not None
    assert rs["ticker"] == "NVDA"
    assert rs["benchmark"] == "$SPX"
    # 1d RS: (110-100)/100 = 10.0, $SPX (5000-4900)/4900 = 2.0408 → RS ≈ 7.9592
    assert rs["windows"][1]["ticker_pct"] == pytest.approx(10.0, rel=1e-4)
    assert rs["windows"][1]["rs"] == pytest.approx(7.9592, rel=1e-4)


@pytest.mark.django_db
def test_with_tickers_no_bars_relative_strength_is_none():
    """When the primary ticker has no daily bars, RS is None (honest coverage)."""
    _spx_bars()  # benchmark present, but primary (NVDA) has no bars
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context(tickers=["NVDA"])
    assert ctx.get("relative_strength") is None


@pytest.mark.django_db
def test_sector_rotation_populated_when_bars_present():
    """sector_rotation includes ETFs that have daily bars."""
    _spx_bars()
    for i, close in enumerate([40, 42, 44, 46, 48, 50]):
        _bar("XLF", i, float(close))

    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context()

    rotation = ctx.get("sector_rotation", [])
    sectors_returned = [r["sector"] for r in rotation]
    assert "XLF" in sectors_returned
    # XLF 5d return: (50-40)/40 * 100 = 25.0
    xlf_row = next(r for r in rotation if r["sector"] == "XLF")
    assert xlf_row["return_pct"] == pytest.approx(25.0, rel=1e-4)
    # RS = 25.0 - 11.1111 = 13.8889
    assert xlf_row["rs"] == pytest.approx(13.8889, rel=1e-4)


@pytest.mark.django_db
def test_sector_rotation_empty_when_no_sector_bars():
    """sector_rotation is [] when no sector ETF has daily bars (even with $SPX bars)."""
    _spx_bars()
    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx = fetch_market_context()
    assert ctx["sector_rotation"] == []


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
def test_cache_key_differs_no_args_vs_ticker():
    """fetch_market_context() and fetch_market_context(tickers=["NVDA"]) use different keys."""
    _nvda_bars()
    _spx_bars()

    with patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES):
        ctx_no_args = fetch_market_context()
        ctx_nvda = fetch_market_context(tickers=["NVDA"])

    assert ctx_no_args.get("relative_strength") is None
    assert ctx_nvda.get("relative_strength") is not None


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
