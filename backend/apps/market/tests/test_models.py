from decimal import Decimal

import pytest
from django.utils import timezone

from apps.market.models import OHLCBar


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
