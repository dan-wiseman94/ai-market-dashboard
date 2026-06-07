import pytest

from apps.observer.triggers import indicators as ind

CLOSES = [float(x) for x in range(1, 60)]  # strictly rising


def test_rsi_rising_is_high():
    v = ind.rsi(CLOSES, 14)
    assert v is not None and v > 90  # all gains -> RSI ~100


def test_rsi_insufficient_none():
    assert ind.rsi([1, 2, 3], 14) is None


def test_sma_spread_pct_positive_when_fast_above_slow():
    v = ind.sma_spread_pct(CLOSES, fast=5, slow=20)
    assert v is not None and v > 0


def test_sma_spread_pct_none_when_insufficient():
    assert ind.sma_spread_pct([1, 2, 3], fast=5, slow=20) is None


def test_dist_from_high():
    assert ind.dist_from_high([10, 12, 11], last=11) == pytest.approx((11 - 12) / 12)


def test_dist_from_low():
    assert ind.dist_from_low([10, 8, 9], last=9) == pytest.approx((9 - 8) / 8)


def test_gap_pct():
    assert ind.gap_pct(today_open=102, prev_close=100) == pytest.approx(0.02)


def test_gap_pct_none_on_zero_prev():
    assert ind.gap_pct(today_open=102, prev_close=0) is None


def test_atr_pct():
    bars = [{"high": 11, "low": 9, "close": 10}] * 20
    v = ind.atr_pct(bars, period=14, last=10)
    assert v is not None and v >= 0
