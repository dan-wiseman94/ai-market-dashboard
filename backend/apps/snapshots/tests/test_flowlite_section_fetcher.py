"""Tests for the `flowlite` snapshot section fetcher (apps.snapshots.services._FETCHERS)."""

from unittest.mock import patch

import apps.snapshots.services as snapshot_services

_CANNED = {
    "proxy_note": "volume-based flow proxy — not fund-flow data",
    "volume_z": [],
    "put_call_delta": None,
    "unusual": [],
}


def test_flowlite_fetcher_passes_watchlist_and_picked_primary():
    with patch.object(snapshot_services, "build_flowlite_payload", return_value=_CANNED) as m:
        out = snapshot_services._FETCHERS["flowlite"](
            watchlist_tickers=["NVDA", "SPY"], ohlc_ticker=None
        )
    m.assert_called_once_with(watchlist_tickers=["NVDA", "SPY"], primary="NVDA")
    assert out == {"data": _CANNED}


def test_flowlite_fetcher_prefers_explicit_ohlc_ticker_as_primary():
    with patch.object(snapshot_services, "build_flowlite_payload", return_value=_CANNED) as m:
        snapshot_services._FETCHERS["flowlite"](
            watchlist_tickers=["NVDA", "SPY"], ohlc_ticker="TSLA"
        )
    m.assert_called_once_with(watchlist_tickers=["NVDA", "SPY"], primary="TSLA")


def test_flowlite_fetcher_empty_watchlist_defaults_primary_to_spy():
    with patch.object(snapshot_services, "build_flowlite_payload", return_value=_CANNED) as m:
        snapshot_services._FETCHERS["flowlite"](watchlist_tickers=[], ohlc_ticker=None)
    m.assert_called_once_with(watchlist_tickers=[], primary="SPY")
