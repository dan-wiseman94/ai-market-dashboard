"""``trading_day_forward_returns`` (batched) must equal ``trading_day_forward_return_pct``.

The provider leaderboard uses the batched, O(1)-query variant. This pins that the
batched result is byte-identical to the per-row helper on the same data — across the
split-adjustment and coverage-gap paths — so only the query count differs, not the numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.market.models import CorporateAction, OHLCBar
from apps.market.returns import trading_day_forward_return_pct, trading_day_forward_returns

# 10 NYSE sessions: Apr 6-10 and 13-17, 2026 (two Mon-Fri weeks) at ~16:00 ET (20:00 UTC).
_DAYS = [datetime(2026, 4, d, 20, 0, tzinfo=UTC) for d in (6, 7, 8, 9, 10, 13, 14, 15, 16, 17)]


def _bar(ticker: str, ts: datetime, close: float) -> None:
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


@pytest.mark.django_db
def test_batched_forward_returns_match_per_run():
    for i, ts in enumerate(_DAYS):
        _bar("AAA", ts, 100.0 + i)
    # 2:1 split ex Apr 14 — a window spanning it must adjust (not read as a -50% crash).
    CorporateAction.objects.create(
        source="mock",
        external_id="aaa-split",
        kind="split",
        ticker="AAA",
        ex_date=datetime(2026, 4, 14).date(),
        ratio=Decimal("2"),
    )
    requests = [
        ("AAA", _DAYS[0]),  # one session forward
        ("AAA", _DAYS[2]),  # spans the split for fh=48
        ("AAA", _DAYS[8]),  # near the end of the series
        ("AAA", _DAYS[9] + timedelta(days=40)),  # far future → coverage gap (None)
    ]
    for fh in (24, 48):
        batched = trading_day_forward_returns(requests, fh)
        per_run = [trading_day_forward_return_pct(t, at, fh) for t, at in requests]
        assert batched == per_run, f"fh={fh}: batched={batched} per_run={per_run}"


@pytest.mark.django_db
def test_batched_forward_returns_empty_input():
    assert trading_day_forward_returns([], 24) == []
