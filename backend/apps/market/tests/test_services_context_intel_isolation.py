"""Failure isolation between relative_strength and sector_rotation in _fetch.

Each intel call degrades independently: a raising sector_rotation must not
clobber a successfully computed relative_strength (and vice versa), and each
failure logs a warning. Setup mirrors test_services_context_intel.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from apps.market import cache as cache_module
from apps.market.models import OHLCBar
from apps.market.services.context import CONTEXT_SYMBOLS, fetch_market_context

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
    for i, close in enumerate([60, 70, 80, 90, 100, 110]):
        _bar("NVDA", i, float(close))


def _spx_bars() -> None:
    for i, close in enumerate([4500, 4600, 4700, 4800, 4900, 5000]):
        _bar("$SPX", i, float(close))


def _xlf_bars() -> None:
    for i, close in enumerate([40, 42, 44, 46, 48, 50]):
        _bar("XLF", i, float(close))


@pytest.mark.django_db
def test_sector_rotation_failure_preserves_relative_strength(caplog):
    """A raising sector_rotation must not reset an already-computed RS."""
    _nvda_bars()
    _spx_bars()
    with (
        patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES),
        patch(
            "apps.market.services.intel.sector_rotation",
            side_effect=RuntimeError("boom"),
        ),
        caplog.at_level(logging.WARNING, logger="apps.market.services.context"),
    ):
        ctx = fetch_market_context(tickers=["NVDA"])

    rs = ctx.get("relative_strength")
    assert rs is not None
    assert rs["ticker"] == "NVDA"
    assert ctx["sector_rotation"] == []
    assert any("intel.sector_rotation failed" in m for m in caplog.messages)


@pytest.mark.django_db
def test_relative_strength_failure_preserves_sector_rotation(caplog):
    """A raising relative_strength must not reset an independently computed rotation."""
    _spx_bars()
    _xlf_bars()
    with (
        patch("apps.market.services.context.fetch_quotes", return_value=_FAKE_QUOTES),
        patch(
            "apps.market.services.intel.relative_strength",
            side_effect=RuntimeError("boom"),
        ),
        caplog.at_level(logging.WARNING, logger="apps.market.services.context"),
    ):
        ctx = fetch_market_context(tickers=["NVDA"])

    assert ctx.get("relative_strength") is None
    rotation = ctx.get("sector_rotation", [])
    assert "XLF" in [r["sector"] for r in rotation]
    assert any("intel.relative_strength failed for NVDA" in m for m in caplog.messages)
