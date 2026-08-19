"""Tests for market.ingest_daily_bars task.

Patching strategy: the task uses function-local imports, so we patch at the
canonical module path (`apps.market.services.ohlc.fetch_ohlc`). Any caller
that imports from there — including the task's own local import — gets the
patched version.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services.context import MACRO, SECTOR_ETFS
from apps.market.tasks import ingest_daily_bars
from apps.profiles.models import Watchlist, WatchlistSymbol


def _expected_universe(extra_tickers: list[str]) -> set[str]:
    """Compute the expected universe set for a given watchlist."""
    return {s.upper() for s in [*extra_tickers, "$SPX", "QQQ", *SECTOR_ETFS, *MACRO.values()] if s}


@pytest.mark.django_db
def test_universe_coverage_and_timeframe():
    """Every ticker from watchlist + fixed + sector ETFs + macro proxies is
    fetched with timeframe='1d', and only those tickers."""
    wl = Watchlist.objects.create(name="Core")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="NVDA")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="AAPL")

    expected = _expected_universe(["NVDA", "AAPL"])

    with patch("apps.market.services.ohlc.fetch_ohlc", return_value=[]) as mock_fetch:
        ingest_daily_bars()

    called_tickers = {c.args[0] for c in mock_fetch.call_args_list}
    assert called_tickers == expected

    for c in mock_fetch.call_args_list:
        assert c.kwargs.get("timeframe") == "1d", (
            f"Expected timeframe='1d' but got {c.kwargs} for {c.args}"
        )


@pytest.mark.django_db
def test_return_shape_all_success():
    """requested == ingested == universe size on full success."""
    wl = Watchlist.objects.create(name="Core")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="NVDA")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="AAPL")

    expected_size = len(_expected_universe(["NVDA", "AAPL"]))

    with patch("apps.market.services.ohlc.fetch_ohlc", return_value=[]):
        result = ingest_daily_bars()

    assert result["requested"] == expected_size
    assert result["ingested"] == expected_size


@pytest.mark.django_db
def test_never_raises_one_symbol_fails():
    """Task must not raise even when one symbol's fetch raises. The failing symbol
    is excluded from ingested count; all other symbols are still attempted."""
    wl = Watchlist.objects.create(name="Core")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="NVDA")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="AAPL")

    universe = sorted(_expected_universe(["NVDA", "AAPL"]))
    failing_sym = "$TNX"
    assert failing_sym in universe, f"$TNX must be in universe; got {universe}"

    def side_effect(sym, *, timeframe, bars=60):
        if sym == failing_sym:
            raise RuntimeError("Schwab returned an error for $TNX")
        return []

    with patch("apps.market.services.ohlc.fetch_ohlc", side_effect=side_effect):
        result = ingest_daily_bars()

    assert result["requested"] == len(universe)
    assert result["ingested"] == len(universe) - 1, (
        f"Expected ingested={len(universe) - 1} (one failure) but got {result}"
    )


@pytest.mark.django_db
def test_empty_watchlist_still_includes_fixed_universe():
    """With no watchlist rows the fixed symbols are still ingested."""
    fixed = _expected_universe([])

    with patch("apps.market.services.ohlc.fetch_ohlc", return_value=[]) as mock_fetch:
        result = ingest_daily_bars()

    called_tickers = {c.args[0] for c in mock_fetch.call_args_list}
    assert called_tickers == fixed
    assert result["requested"] == len(fixed)
    assert result["ingested"] == len(fixed)


def test_beat_registration():
    """Beat schedule must include the ingest-daily-bars entry with the correct task name."""
    from config.celery import app

    assert "ingest-daily-bars" in app.conf.beat_schedule, (
        "Beat schedule missing 'ingest-daily-bars' entry"
    )
    entry = app.conf.beat_schedule["ingest-daily-bars"]
    assert entry["task"] == "market.ingest_daily_bars", (
        f"Expected task='market.ingest_daily_bars' but got {entry['task']!r}"
    )
