"""Property-based tests for NYSE market hours (apps.observer.services.market_hours).

Uses pandas-market-calendars (cached at import) — no DB. The strong, always-true
invariant: the US equity market is never open on a Saturday or Sunday.
"""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from apps.observer.services.market_hours import is_market_open

# 2020-01-04 is a Saturday. Stepping whole weeks keeps it Saturday; +0/+1 day → Sat/Sun.
_SATURDAY_ANCHOR = datetime(2020, 1, 4, tzinfo=UTC)


@given(
    weeks=st.integers(min_value=0, max_value=780),  # ~2020..2035
    weekend_day=st.integers(min_value=0, max_value=1),  # 0=Sat, 1=Sun
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
)
def test_market_is_closed_on_weekends(weeks, weekend_day, hour, minute):
    at = (
        _SATURDAY_ANCHOR
        + timedelta(weeks=weeks, days=weekend_day)
        + timedelta(hours=hour, minutes=minute)
    )
    assert at.weekday() in (5, 6)  # guard: really a weekend
    assert is_market_open(at) is False
