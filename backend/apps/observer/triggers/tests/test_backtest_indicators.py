from datetime import UTC, datetime, timedelta

import pytest

from apps.market.models import OHLCBar
from apps.observer.triggers.backtest import backtest


@pytest.mark.django_db
def test_backtest_rsi_and_crossing():
    # 40 rising daily bars for NVDA — each bar gets a distinct ts
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(40):
        OHLCBar.objects.create(
            ticker="NVDA",
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=1000,
        )
    cond = {
        "metric": "rsi",
        "ticker": "NVDA",
        "window": "1d",
        "op": ">",
        "value": 70,
        "params": {"period": 14},
    }
    matches = backtest(
        cond,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 3, 1, tzinfo=UTC),
        timeframe="1d",
    )
    assert len(matches) > 0  # rising series -> RSI>70 on later bars


@pytest.mark.django_db
def test_backtest_price_crossing_now_matches():
    closes = [100, 100, 105]  # crosses_above 102 on the 3rd bar
    for i, c in enumerate(closes):
        OHLCBar.objects.create(
            ticker="SPY",
            timeframe="1d",
            ts=datetime(2026, 1, 1 + i, tzinfo=UTC),
            open=c,
            high=c,
            low=c,
            close=c,
            volume=1,
        )
    cond = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 102}
    matches = backtest(
        cond,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 2, 1, tzinfo=UTC),
        timeframe="1d",
    )
    assert len(matches) == 1  # exactly one crossing must fire
