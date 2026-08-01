"""Objectives that scan across names (breakout scans, relative strength) need
per-name price history — a single primary ticker's bars can't answer them. The
ohlc section carries compact daily history for the rest of the watchlist,
best-effort per ticker and bounded."""

from unittest.mock import patch

from apps.snapshots.services import _fetch_ohlc_section

_BAR = {"ts": "2026-07-25T04:00:00+00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 9}


def test_watchlist_names_get_daily_history_alongside_primary():
    with (
        patch("apps.snapshots.services.fetch_ohlc_24h", return_value=[_BAR]),
        patch("apps.snapshots.services.fetch_ohlc", return_value=[_BAR]) as m,
    ):
        out = _fetch_ohlc_section(
            watchlist_tickers=["$SPX", "QQQ", "IWM"], ohlc_ticker="$SPX", ohlc_timeframe="1m"
        )
    wl = out["data"]["watchlist_daily"]
    assert set(wl) == {"QQQ", "IWM"}  # primary excluded — it has the full intraday series
    assert m.call_count == 2
    for call in m.call_args_list:
        assert call.kwargs["timeframe"] == "1d"


def test_one_failing_ticker_does_not_kill_the_section():
    def flaky(ticker, *, timeframe, bars):
        if ticker == "QQQ":
            raise RuntimeError("boom")
        return [_BAR]

    with (
        patch("apps.snapshots.services.fetch_ohlc_24h", return_value=[_BAR]),
        patch("apps.snapshots.services.fetch_ohlc", side_effect=flaky),
    ):
        out = _fetch_ohlc_section(
            watchlist_tickers=["SPY", "QQQ", "IWM"], ohlc_ticker="SPY", ohlc_timeframe="1m"
        )
    assert set(out["data"]["watchlist_daily"]) == {"IWM"}


def test_watchlist_daily_ticker_cap():
    tickers = [f"T{i}" for i in range(12)]
    with (
        patch("apps.snapshots.services.fetch_ohlc_24h", return_value=[_BAR]),
        patch("apps.snapshots.services.fetch_ohlc", return_value=[_BAR]) as m,
    ):
        _fetch_ohlc_section(watchlist_tickers=tickers, ohlc_ticker="ZZZ", ohlc_timeframe="1m")
    assert m.call_count == 8


def test_daily_primary_also_gets_watchlist_history():
    with patch("apps.snapshots.services.fetch_ohlc", return_value=[_BAR]):
        out = _fetch_ohlc_section(
            watchlist_tickers=["SPY", "QQQ"], ohlc_timeframe="1d", ohlc_bars=30
        )
    assert "QQQ" in out["data"]["watchlist_daily"]
    assert "SPY" not in out["data"]["watchlist_daily"]


def test_empty_watchlist_omits_the_key():
    with patch("apps.snapshots.services.fetch_ohlc_24h", return_value=[_BAR]):
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="1m")
    assert "watchlist_daily" not in out["data"]
