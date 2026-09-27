"""Indicator math is pure: list in, float out. No DB, no cache."""

from __future__ import annotations

import pytest

from apps.market.services.indicator import compute


def test_sma_simple_mean() -> None:
    assert compute("SMA", [1.0, 2.0, 3.0, 4.0, 5.0], period=5) == pytest.approx(3.0)


def test_ema_weights_recent_more_than_old() -> None:
    flat = compute("EMA", [1.0] * 20, period=10)
    assert flat == pytest.approx(1.0)
    step = compute("EMA", [1.0] * 10 + [2.0] * 10, period=10)
    assert step is not None
    assert 1.5 < step < 2.0


def test_rsi_all_losses_is_0() -> None:
    closes = [float(30 - i) for i in range(1, 30)]
    assert compute("RSI", closes, period=14) == pytest.approx(0.0, abs=0.5)


def test_atr_uses_true_range() -> None:
    # Gap bars, so true range differs from high-low: a gap up (|high - prev close| = 2
    # beats the 1.5 range) then a gap down (|low - prev close| = 2 beats the 1.0 range).
    # A plain high-low average would give 1.25.
    bars = [
        {"high": 10, "low": 8, "close": 9},
        {"high": 11, "low": 9.5, "close": 10},
        {"high": 9, "low": 8, "close": 8.5},
    ]
    assert compute("ATR", bars, period=2) == pytest.approx(2.0)


def test_unknown_indicator_raises() -> None:
    with pytest.raises(ValueError, match="Unknown indicator"):
        compute("NOPE", [1.0, 2.0], period=2)
