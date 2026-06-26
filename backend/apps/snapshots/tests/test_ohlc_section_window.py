from unittest.mock import patch

from apps.snapshots.services import _fetch_ohlc_section


def test_intraday_uses_24h_window():
    with patch(
        "apps.snapshots.services.fetch_ohlc_24h", return_value=[{"ts": "t", "close": 1}]
    ) as m:
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="5m")
    m.assert_called_once_with("SPY", timeframe="5m")
    assert out["data"]["window"] == "24h"
    assert out["data"]["timeframe"] == "5m"
    assert out["data"]["bars"] == [{"ts": "t", "close": 1}]
    assert "coarse_timeframe" not in out["data"]


def test_1m_marks_coarse_timeframe():
    with patch("apps.snapshots.services.fetch_ohlc_24h", return_value=[]):
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="1m")
    assert out["data"]["coarse_timeframe"] == "5m"


def test_daily_uses_fixed_bar_count():
    with patch("apps.snapshots.services.fetch_ohlc", return_value=[{"ts": "t", "close": 1}]) as m:
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="1d", ohlc_bars=60)
    m.assert_called_once_with("SPY", timeframe="1d", bars=60)
    assert "window" not in out["data"]
