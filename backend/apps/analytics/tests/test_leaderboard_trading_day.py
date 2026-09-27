from datetime import UTC, datetime

import pytest

from apps.market.returns import trading_day_forward_return_pct


@pytest.mark.django_db
def test_forward_return_none_when_no_target_bar(mk_bar):
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    mk_bar("SPY", at, 100.0)  # only the t0 bar; no bar near the target session
    assert trading_day_forward_return_pct("SPY", at, 24) is None
