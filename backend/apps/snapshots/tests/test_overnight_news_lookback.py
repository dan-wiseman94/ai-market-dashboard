from datetime import UTC, datetime

from apps.snapshots.services import _overnight_news_lookback_hours


def test_lookback_rounds_up_hours_since_close():
    as_of = datetime(2026, 5, 28, 20, 0, tzinfo=UTC)  # prior close
    now = datetime(2026, 5, 29, 12, 30, tzinfo=UTC)  # 16.5h later
    assert _overnight_news_lookback_hours(as_of, now=now) == 17


def test_lookback_clamped_to_floor_1():
    as_of = datetime(2026, 5, 29, 11, 59, tzinfo=UTC)
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)  # 1 minute
    assert _overnight_news_lookback_hours(as_of, now=now) == 1


def test_lookback_clamped_to_ceiling_48():
    as_of = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)  # >48h ago (long weekend/holiday)
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    assert _overnight_news_lookback_hours(as_of, now=now) == 48
