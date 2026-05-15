from decimal import Decimal

import pytest
from django.utils import timezone

from apps.market.models import MarketContext, OHLCBar, Position, Quote


@pytest.mark.django_db
def test_quote_create():
    q = Quote.objects.create(
        ticker="SPY",
        last=Decimal("550.12"),
        bid=Decimal("550.11"),
        ask=Decimal("550.13"),
        volume=123456,
        ts=timezone.now(),
    )
    assert q.ticker == "SPY"
    assert q.last == Decimal("550.12")


@pytest.mark.django_db
def test_ohlcbar_unique_per_ticker_timeframe_ts():
    ts = timezone.now().replace(second=0, microsecond=0)
    OHLCBar.objects.create(
        ticker="SPY",
        timeframe="1m",
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("1"),
        close=Decimal("2"),
        volume=100,
        ts=ts,
    )
    with pytest.raises(Exception, match=""):
        OHLCBar.objects.create(
            ticker="SPY",
            timeframe="1m",
            open=Decimal("1"),
            high=Decimal("2"),
            low=Decimal("1"),
            close=Decimal("2"),
            volume=100,
            ts=ts,
        )


@pytest.mark.django_db
def test_position_create():
    p = Position.objects.create(
        ticker="NVDA",
        qty=Decimal("100"),
        avg_cost=Decimal("800.50"),
        mkt_value=Decimal("85000"),
        unrealized_pl=Decimal("4950"),
        day_pl=Decimal("250"),
        as_of=timezone.now(),
    )
    assert p.qty == Decimal("100")


@pytest.mark.django_db
def test_market_context_create():
    mc = MarketContext.objects.create(
        spy_last=Decimal("550"),
        qqq_last=Decimal("480"),
        vix_last=Decimal("14"),
        sectors={"XLK": 215.4, "XLF": 45.2},
        breadth={"advance_count": 1200, "decline_count": 900},
        as_of=timezone.now(),
    )
    assert mc.sectors["XLK"] == 215.4
