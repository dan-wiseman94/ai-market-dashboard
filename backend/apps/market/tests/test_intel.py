"""Unit tests for apps.market.services.intel.

All assertions use hand-verified exact values from the bar fixtures created
below.  No assert-not-None-only tests.

Bar layout
----------
We create daily ("1d") bars for two tickers plus the benchmark ($SPX):

NVDA bars (6 total, days 0-5, closes 60/70/80/90/100/110):
  ts=BASE+0d close=60
  ts=BASE+1d close=70
  ts=BASE+2d close=80
  ts=BASE+3d close=90
  ts=BASE+4d close=100
  ts=BASE+5d close=110   <- most recent

  return_over_sessions("NVDA", 1):  (110-100)/100*100 = 10.0
  return_over_sessions("NVDA", 5):  (110-60)/60*100   = 83.3333 -> 83.3333

$SPX bars (6 total, days 0-5, closes 4500/4600/4700/4800/4900/5000):
  ts=BASE+0d close=4500
  ts=BASE+5d close=5000  <- most recent

  return_over_sessions("$SPX", 1):  (5000-4900)/4900*100 = 2.0408163... -> 2.0408
  return_over_sessions("$SPX", 5):  (5000-4500)/4500*100 = 11.1111...   -> 11.1111

  RS 1d: round(10.0 - 2.0408, 4)    = 7.9592
  RS 5d: round(83.3333 - 11.1111,4) = 72.2222

XLK bars (6 total, days 0-5, closes 180/182/184/186/188/190):
  return_over_sessions("XLK", 5):  (190-180)/180*100 = 5.5556
  XLK RS vs $SPX: round(5.5556 - 11.1111, 4) = -5.5556 (laggard)

XLF bars (6 total, days 0-5, closes 40/42/44/46/48/50):
  return_over_sessions("XLF", 5):  (50-40)/40*100 = 25.0
  XLF RS vs $SPX: round(25.0 - 11.1111, 4) = 13.8889 (leader)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.market.models import OHLCBar
from apps.market.services.intel import (
    BENCHMARK,
    breadth_stats,
    factor_returns,
    relative_strength,
    return_over_sessions,
    sector_rotation,
)

BASE = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
DAY = timedelta(days=1)


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
    """6 NVDA daily bars: closes 60,70,80,90,100,110 (day 0..5)."""
    for i, close in enumerate([60, 70, 80, 90, 100, 110]):
        _bar("NVDA", i, float(close))


def _spx_bars() -> None:
    """6 $SPX daily bars: closes 4500,4600,4700,4800,4900,5000 (day 0..5)."""
    for i, close in enumerate([4500, 4600, 4700, 4800, 4900, 5000]):
        _bar("$SPX", i, float(close))


class TestReturnOverSessions:
    @pytest.mark.django_db
    def test_1_session_nvda(self):
        """(110-100)/100 * 100 = 10.0"""
        _nvda_bars()
        result = return_over_sessions("NVDA", 1)
        assert result == pytest.approx(10.0, rel=1e-4)

    @pytest.mark.django_db
    def test_5_session_nvda(self):
        """(110-60)/60 * 100 = 83.3333..."""
        _nvda_bars()
        result = return_over_sessions("NVDA", 5)
        assert result == pytest.approx(83.3333, rel=1e-4)

    @pytest.mark.django_db
    def test_1_session_spx(self):
        """(5000-4900)/4900 * 100 = 2.0408..."""
        _spx_bars()
        result = return_over_sessions("$SPX", 1)
        assert result == pytest.approx(2.0408, rel=1e-4)

    @pytest.mark.django_db
    def test_5_session_spx(self):
        """(5000-4500)/4500 * 100 = 11.1111..."""
        _spx_bars()
        result = return_over_sessions("$SPX", 5)
        assert result == pytest.approx(11.1111, rel=1e-4)

    @pytest.mark.django_db
    def test_none_when_ticker_has_no_bars(self):
        _nvda_bars()
        assert return_over_sessions("ZZZZ", 1) is None

    @pytest.mark.django_db
    def test_none_when_only_one_bar_and_need_two(self):
        """sessions=1 needs 2 bars; with only 1 bar returns None."""
        _bar("SOLO", 0, 100.0)
        assert return_over_sessions("SOLO", 1) is None

    @pytest.mark.django_db
    def test_none_when_exactly_sessions_bars_but_not_sessions_plus_one(self):
        """sessions=5 needs 6 bars; with only 5 bars returns None."""
        for i in range(5):
            _bar("FEW", i, float(100 + i))
        assert return_over_sessions("FEW", 5) is None

    @pytest.mark.django_db
    def test_returns_value_when_exactly_sessions_plus_one_bars(self):
        """sessions=1 needs exactly 2 bars; should return a value."""
        _bar("PAIR", 0, 100.0)
        _bar("PAIR", 1, 105.0)
        result = return_over_sessions("PAIR", 1)
        # (105-100)/100*100 = 5.0
        assert result == pytest.approx(5.0, rel=1e-4)

    @pytest.mark.django_db
    def test_ignores_non_daily_bars(self):
        """Only timeframe='1d' bars count; '1m' bars are ignored."""
        OHLCBar.objects.create(
            ticker="INTRA",
            timeframe="1m",
            ts=BASE + DAY,
            open=200.0,
            high=200.0,
            low=200.0,
            close=200.0,
            volume=1,
        )
        assert return_over_sessions("INTRA", 1) is None

    @pytest.mark.django_db
    def test_lowercase_ticker_normalised(self):
        """Ticker lookup is case-insensitive (stored upper, queried upper)."""
        _nvda_bars()
        result = return_over_sessions("nvda", 1)
        assert result == pytest.approx(10.0, rel=1e-4)

    @pytest.mark.django_db
    def test_none_when_prior_close_is_zero(self):
        """Division guard: prior close of 0 → None."""
        _bar("ZERO", 0, 0.0)
        _bar("ZERO", 1, 100.0)
        assert return_over_sessions("ZERO", 1) is None


class TestRelativeStrength:
    @pytest.mark.django_db
    def test_rs_1d_and_5d_hand_verified(self):
        """
        1d RS: round(10.0 - 2.0408, 4) = 7.9592
        5d RS: round(83.3333 - 11.1111, 4) = 72.2222
        """
        _nvda_bars()
        _spx_bars()
        result = relative_strength("NVDA")
        assert result is not None
        assert result["ticker"] == "NVDA"
        assert result["benchmark"] == BENCHMARK

        w = result["windows"]

        assert w[1]["ticker_pct"] == pytest.approx(10.0, rel=1e-4)
        assert w[1]["benchmark_pct"] == pytest.approx(2.0408, rel=1e-4)
        assert w[1]["rs"] == pytest.approx(7.9592, rel=1e-4)

        assert w[5]["ticker_pct"] == pytest.approx(83.3333, rel=1e-4)
        assert w[5]["benchmark_pct"] == pytest.approx(11.1111, rel=1e-4)
        assert w[5]["rs"] == pytest.approx(72.2222, rel=1e-4)

    @pytest.mark.django_db
    def test_returns_none_when_ticker_has_no_bars(self):
        """When the primary ticker has no bars at all, returns None."""
        _spx_bars()
        assert relative_strength("ZZZZ") is None

    @pytest.mark.django_db
    def test_returns_none_for_empty_ticker(self):
        assert relative_strength("") is None

    @pytest.mark.django_db
    def test_rs_none_per_window_when_benchmark_missing(self):
        """When benchmark has no bars, rs is None per window but ticker_pct is present."""
        _nvda_bars()
        result = relative_strength("NVDA", benchmark="$SPX")
        assert result is not None  # ticker has bars → not None at top level
        w = result["windows"]
        assert w[1]["ticker_pct"] == pytest.approx(10.0, rel=1e-4)
        assert w[1]["benchmark_pct"] is None
        assert w[1]["rs"] is None

    @pytest.mark.django_db
    def test_rs_none_per_window_when_window_too_thin(self):
        """Only 2 bars: 1d window works, 5d and 20d are None (thin data)."""
        _bar("THIN", 0, 100.0)
        _bar("THIN", 1, 110.0)
        _spx_bars()  # enough for 1d and 5d but not 20d for benchmark
        result = relative_strength("THIN")
        assert result is not None
        w = result["windows"]
        # 1d: THIN has 2 bars → ticker_pct present; but 5d and 20d → None
        assert w[1]["ticker_pct"] == pytest.approx(10.0, rel=1e-4)
        assert w[5]["ticker_pct"] is None
        assert w[20]["ticker_pct"] is None
        assert w[5]["rs"] is None

    @pytest.mark.django_db
    def test_ticker_uppercased_in_result(self):
        _nvda_bars()
        _spx_bars()
        result = relative_strength("nvda")
        assert result is not None
        assert result["ticker"] == "NVDA"

    @pytest.mark.django_db
    def test_custom_benchmark(self):
        """Custom benchmark is used and reflected in result."""
        _nvda_bars()
        for i, close in enumerate([300, 310, 320, 330, 340, 350]):
            _bar("QQQ", i, float(close))
        result = relative_strength("NVDA", benchmark="QQQ")
        assert result is not None
        assert result["benchmark"] == "QQQ"
        # QQQ 1d: (350-340)/340*100 = 2.9412
        # RS 1d: 10.0 - 2.9412 = 7.0588
        w = result["windows"]
        assert w[1]["benchmark_pct"] == pytest.approx(2.9412, rel=1e-4)
        assert w[1]["rs"] == pytest.approx(10.0 - 2.9412, rel=1e-3)


class TestSectorRotation:
    @pytest.mark.django_db
    def test_empty_list_when_no_sector_bars(self):
        """No bars at all for any sector ETF → []."""
        _spx_bars()
        result = sector_rotation()
        assert result == []

    @pytest.mark.django_db
    def test_skips_sectors_with_no_bars(self):
        """Only XLK + XLF have bars; result has only those two."""
        _spx_bars()
        for i, close in enumerate([180, 182, 184, 186, 188, 190]):
            _bar("XLK", i, float(close))
        for i, close in enumerate([40, 42, 44, 46, 48, 50]):
            _bar("XLF", i, float(close))

        result = sector_rotation(sectors=["XLK", "XLF", "XLE"])  # XLE has no bars
        tickers_in_result = [r["sector"] for r in result]
        assert "XLE" not in tickers_in_result
        assert "XLK" in tickers_in_result
        assert "XLF" in tickers_in_result

    @pytest.mark.django_db
    def test_leaders_first_sorted_by_rs(self):
        """
        XLF 5d return: (50-40)/40*100 = 25.0, RS = 25.0 - 11.1111 = 13.8889
        XLK 5d return: (190-180)/180*100 = 5.5556, RS = 5.5556 - 11.1111 = -5.5556
        XLF (leader) must come first, XLK (laggard) second.
        """
        _spx_bars()
        for i, close in enumerate([180, 182, 184, 186, 188, 190]):
            _bar("XLK", i, float(close))
        for i, close in enumerate([40, 42, 44, 46, 48, 50]):
            _bar("XLF", i, float(close))

        result = sector_rotation(sectors=["XLK", "XLF"])
        assert len(result) == 2
        assert result[0]["sector"] == "XLF"
        assert result[0]["return_pct"] == pytest.approx(25.0, rel=1e-4)
        assert result[0]["rs"] == pytest.approx(13.8889, rel=1e-4)
        assert result[1]["sector"] == "XLK"
        assert result[1]["return_pct"] == pytest.approx(5.5556, rel=1e-4)
        assert result[1]["rs"] == pytest.approx(-5.5556, rel=1e-4)

    @pytest.mark.django_db
    def test_rs_none_when_benchmark_missing(self):
        """When benchmark has no bars, rs is None but return_pct is still present."""
        for i, close in enumerate([40, 42, 44, 46, 48, 50]):
            _bar("XLF", i, float(close))

        result = sector_rotation(sectors=["XLF"])
        assert len(result) == 1
        assert result[0]["sector"] == "XLF"
        assert result[0]["return_pct"] == pytest.approx(25.0, rel=1e-4)
        assert result[0]["rs"] is None

    @pytest.mark.django_db
    def test_returns_empty_list_when_no_sectors_provided(self):
        _spx_bars()
        result = sector_rotation(sectors=[])
        assert result == []


def _factor_returns_bars() -> None:
    """Seed bars for factor_returns tests.

    MTUM: 5 sessions, from 100 to 110 (+10%)
    VLUE: 5 sessions, from 100 to 102 (+2%)
    IWM: 5 sessions, from 100 to 101 (+1%)
    SPY: 5 sessions, from 100 to 103 (+3%)
    """
    # MTUM +10% over 5 sessions (need 6 bars for sessions+1)
    for i, close in enumerate([100, 102, 104, 106, 108, 110]):
        _bar("MTUM", i, float(close))
    # VLUE +2% over 5 sessions
    for i, close in enumerate([100, 100.4, 100.8, 101.2, 101.6, 102]):
        _bar("VLUE", i, float(close))
    # IWM +1% over 5 sessions
    for i, close in enumerate([100, 100.2, 100.4, 100.6, 100.8, 101]):
        _bar("IWM", i, float(close))
    # SPY +3% over 5 sessions
    for i, close in enumerate([100, 100.6, 101.2, 101.8, 102.4, 103]):
        _bar("SPY", i, float(close))


def _breadth_stats_bars() -> None:
    """Seed 60 bars for each of 4 tickers for breadth_stats test.

    Designed to produce exactly highs=1, lows=1:
    - XLF: monotonically increasing, ends at span high (100 to 129.5)
    - XLE: monotonically decreasing, ends at span low (130 to 100.5)
    - XLK: interior peak at bar 30 (rises to 115, then falls to 101.5)
    - XLV: interior valley at bar 30 (falls to 85, then rises to 98.5)

    All four tickers have ≥20 bars, so pct_above_sma[20]["n"] == 4;
    all have exactly 60 bars, so min_span_sessions == 60.
    """
    # XLF: closes 100, 100.5, 101, ..., 129.5 (60 bars, monotonically increasing, HIGH)
    for i in range(60):
        _bar("XLF", i, 100.0 + i * 0.5)

    # XLE: closes 130, 129.5, 129, ..., 100.5 (60 bars, monotonically decreasing, LOW)
    for i in range(60):
        _bar("XLE", i, 130.0 - i * 0.5)

    # XLK: interior peak at bar 30 (rises 100 to 115 over bars 0-30,
    #      then falls 115 to 101 over bars 31-59; interior extremum)
    for i in range(31):
        _bar("XLK", i, 100.0 + i * 0.5)  # 100 to 115
    for i in range(31, 60):
        _bar("XLK", i, 115.5 - (i - 30) * 0.5)  # 115 to 101

    # XLV: interior valley at bar 30 (falls 100 to 85.5 over bars 0-29,
    #      then rises 85 to 99.5 over bars 30-59; interior extremum)
    for i in range(30):
        _bar("XLV", i, 100.0 - i * 0.5)  # 100 to 85.5
    for i in range(30, 60):
        _bar("XLV", i, 85.0 + (i - 30) * 0.5)  # 85.0 to 99.5


class TestFactorReturns:
    @pytest.mark.django_db
    def test_factor_returns_shape_and_spreads(self):
        """Test shape, spread calculations, and honest None for unseeded legs."""
        _factor_returns_bars()
        out = factor_returns(["MTUM", "VLUE", "QUAL", "USMV", "IWM", "SPY"])
        assert out["windows"] == [1, 5, 20]
        assert out["etfs"]["MTUM"][5] is not None
        assert out["spreads"]["momentum_minus_value"][5] == round(
            out["etfs"]["MTUM"][5] - out["etfs"]["VLUE"][5], 4
        )
        assert out["etfs"]["QUAL"][5] is None  # unseeded leg → honest None

    @pytest.mark.django_db
    def test_factor_returns_none_when_no_bars(self):
        """No bars at all → None."""
        out = factor_returns(["MTUM", "VLUE"])
        assert out is None


class TestBreadthStats:
    @pytest.mark.django_db
    def test_breadth_stats_counts_and_real_window(self):
        """Test counts and that min_span_sessions reflects actual bars."""
        _breadth_stats_bars()
        out = breadth_stats(["XLK", "XLF", "XLE", "XLV"])
        assert out["pct_above_sma"][20]["n"] == 4
        assert out["highs"] == 1 and out["lows"] == 1
        assert out["min_span_sessions"] == 60  # labels the REAL window, not 252

    @pytest.mark.django_db
    def test_breadth_stats_none_when_thin(self):
        """< 3 usable tickers → None."""
        out = breadth_stats(["XLK"])
        assert out is None
