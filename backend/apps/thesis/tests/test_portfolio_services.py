"""Layer 2: P&L service tests — unrealized (mark-to-market) and realized P&L.

Hand-computed expected values for LONG and SHORT positions.
Coverage-gap (no OHLC bar) returns None fields — never raises.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.market.models import OHLCBar
from apps.profiles.models import TradingProfile
from apps.thesis.models import Position
from apps.thesis.portfolio_service import realized_pnl, unrealized_pnl

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="Test Profile", style="day trader")


@pytest.fixture
def long_position(db, profile):
    """Long 100 shares of NVDA at $450 avg cost."""
    return Position.objects.create(
        ticker="NVDA",
        direction="long",
        quantity=Decimal("100.0000"),
        avg_cost=Decimal("450.0000"),
        profile=profile,
    )


@pytest.fixture
def short_position(db, profile):
    """Short 50 shares of TSLA at $250 avg cost."""
    return Position.objects.create(
        ticker="TSLA",
        direction="short",
        quantity=Decimal("50.0000"),
        avg_cost=Decimal("250.0000"),
        profile=profile,
    )


def _seed_bar(ticker: str, close: float) -> OHLCBar:
    """Seed a daily OHLC bar with ts = now so nearest_bar_close finds it."""
    return OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
        ts=timezone.now(),
    )


# ---------------------------------------------------------------------------
# unrealized_pnl — LONG
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unrealized_pnl_long_profit(long_position):
    """Long position: price rises from $450 to $480, profit = (480-450)*100 = $3 000."""
    _seed_bar("NVDA", 480.0)
    result = unrealized_pnl(long_position)

    # last price
    assert result["last"] == pytest.approx(480.0)
    # market_value = 480 * 100
    assert result["market_value"] == pytest.approx(48_000.0)
    # unrealized_pnl = (480 - 450) * 100 * +1 = 3 000
    assert result["unrealized_pnl"] == pytest.approx(3_000.0)
    # unrealized_pct = 3000 / (450*100) * 100 = 6.666...%
    assert result["unrealized_pct"] == pytest.approx(6.666_666, rel=1e-4)


@pytest.mark.django_db
def test_unrealized_pnl_long_loss(long_position):
    """Long position: price falls from $450 to $420, loss = (420-450)*100 = -$3 000."""
    _seed_bar("NVDA", 420.0)
    result = unrealized_pnl(long_position)

    assert result["last"] == pytest.approx(420.0)
    assert result["market_value"] == pytest.approx(42_000.0)
    # (420 - 450) * 100 * +1 = -3 000
    assert result["unrealized_pnl"] == pytest.approx(-3_000.0)
    # -3000 / 45000 * 100 = -6.666...%
    assert result["unrealized_pct"] == pytest.approx(-6.666_666, rel=1e-4)


# ---------------------------------------------------------------------------
# unrealized_pnl — SHORT
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unrealized_pnl_short_profit(short_position):
    """Short 50 TSLA at $250; price falls to $220: profit = (250-220)*50 = $1 500.

    Short convention: sign = -1, so pnl = (last - avg_cost) * qty * -1.
    (220 - 250) * 50 * -1 = (-30) * 50 * -1 = +1 500.
    market_value = last * quantity = 220 * 50 = 11 000 (absolute exposure).
    cost_basis = 250 * 50 = 12 500.
    pct = 1500 / 12500 * 100 = 12.0%.
    """
    _seed_bar("TSLA", 220.0)
    result = unrealized_pnl(short_position)

    assert result["last"] == pytest.approx(220.0)
    assert result["market_value"] == pytest.approx(11_000.0)
    assert result["unrealized_pnl"] == pytest.approx(1_500.0)
    assert result["unrealized_pct"] == pytest.approx(12.0)


@pytest.mark.django_db
def test_unrealized_pnl_short_loss(short_position):
    """Short 50 TSLA at $250; price rises to $280: loss = (280-250)*50*-1 = -$1 500."""
    _seed_bar("TSLA", 280.0)
    result = unrealized_pnl(short_position)

    assert result["last"] == pytest.approx(280.0)
    assert result["market_value"] == pytest.approx(14_000.0)
    # (280 - 250) * 50 * -1 = -1 500
    assert result["unrealized_pnl"] == pytest.approx(-1_500.0)
    # -1500 / 12500 * 100 = -12.0%
    assert result["unrealized_pct"] == pytest.approx(-12.0)


# ---------------------------------------------------------------------------
# Coverage-gap: no OHLC bar — returns None fields, never raises
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unrealized_pnl_no_bar_returns_none_fields(long_position):
    """When no OHLC bar exists for the ticker, all computed fields are None (not 0, not raises)."""
    # No bar seeded for NVDA
    result = unrealized_pnl(long_position)

    assert result["last"] is None
    assert result["market_value"] is None
    assert result["unrealized_pnl"] is None
    assert result["unrealized_pct"] is None
    # Function must return a dict (not raise)
    assert isinstance(result, dict)


@pytest.mark.django_db
def test_unrealized_pnl_no_bar_does_not_raise(short_position):
    """Coverage gap on short position also returns None dict, no exception."""
    # No bar seeded for TSLA
    result = unrealized_pnl(short_position)
    assert result["unrealized_pnl"] is None
    assert result["last"] is None


# ---------------------------------------------------------------------------
# realized_pnl helper
# ---------------------------------------------------------------------------


def test_realized_pnl_long_profit():
    """Long: close 100 shares of NVDA at $500 (cost $450). Profit = (500-450)*100 = $5 000."""
    pnl = realized_pnl(
        avg_cost=Decimal("450.0000"),
        close_price=Decimal("500.0000"),
        quantity=Decimal("100.0000"),
        direction="long",
    )
    assert float(pnl) == pytest.approx(5_000.0)


def test_realized_pnl_long_loss():
    """Long: close 100 shares of NVDA at $400 (cost $450). Loss = (400-450)*100 = -$5 000."""
    pnl = realized_pnl(
        avg_cost=Decimal("450.0000"),
        close_price=Decimal("400.0000"),
        quantity=Decimal("100.0000"),
        direction="long",
    )
    assert float(pnl) == pytest.approx(-5_000.0)


def test_realized_pnl_short_profit():
    """Short: close 50 TSLA at $200 (cost $250). Profit = (250-200)*50 = $2 500.

    realized_pnl = (close_price - avg_cost) * qty * sign
    sign for short = -1
    (200 - 250) * 50 * -1 = (-50)*50*(-1) = +2 500.
    """
    pnl = realized_pnl(
        avg_cost=Decimal("250.0000"),
        close_price=Decimal("200.0000"),
        quantity=Decimal("50.0000"),
        direction="short",
    )
    assert float(pnl) == pytest.approx(2_500.0)


def test_realized_pnl_short_loss():
    """Short: close 50 TSLA at $300 (cost $250). Loss = (300-250)*50*-1 = -$2 500."""
    pnl = realized_pnl(
        avg_cost=Decimal("250.0000"),
        close_price=Decimal("300.0000"),
        quantity=Decimal("50.0000"),
        direction="short",
    )
    assert float(pnl) == pytest.approx(-2_500.0)
