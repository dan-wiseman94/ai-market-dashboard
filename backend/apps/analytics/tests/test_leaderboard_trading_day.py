from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.market.models import OHLCBar
from apps.market.returns import trading_day_forward_return_pct


def _bar(ticker, ts, close):
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1h",
        open=close,
        high=close,
        low=close,
        close=Decimal(str(close)),
        volume=1,
        ts=ts,
    )


@pytest.mark.django_db
def test_forward_return_uses_next_trading_session():
    # capture Wed 2026-04-15 20:00 UTC (close); +1 session = Thu 2026-04-16 close
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    _bar("SPY", at, 100.0)
    _bar("SPY", datetime(2026, 4, 16, 20, 0, tzinfo=UTC), 110.0)
    ret = trading_day_forward_return_pct("SPY", at, 24)
    assert ret == pytest.approx(10.0)


@pytest.mark.django_db
def test_forward_return_none_when_no_target_bar():
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    _bar("SPY", at, 100.0)  # only the t0 bar; no bar near the target session
    assert trading_day_forward_return_pct("SPY", at, 24) is None
