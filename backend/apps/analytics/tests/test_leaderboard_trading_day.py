from datetime import UTC, datetime

import pytest

from apps.market.returns import trading_day_forward_return_pct


@pytest.mark.django_db
def test_forward_return_uses_next_trading_session(mk_bar):
    # capture Wed 2026-04-15 20:00 UTC (close); +1 session = Thu 2026-04-16 close
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    mk_bar("SPY", at, 100.0)
    mk_bar("SPY", datetime(2026, 4, 16, 20, 0, tzinfo=UTC), 110.0)
    ret = trading_day_forward_return_pct("SPY", at, 24)
    assert ret == pytest.approx(10.0)


@pytest.mark.django_db
def test_forward_return_none_when_no_target_bar(mk_bar):
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    mk_bar("SPY", at, 100.0)  # only the t0 bar; no bar near the target session
    assert trading_day_forward_return_pct("SPY", at, 24) is None
