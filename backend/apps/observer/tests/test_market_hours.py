from datetime import datetime

from freezegun import freeze_time

from apps.observer.services.market_hours import is_market_open, market_status


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET → market open
def test_is_market_open_during_session():
    assert is_market_open() is True


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET
def test_market_status_returns_open_during_session():
    s = market_status()
    assert s["is_open"] is True
    assert s["next_close"] is not None
    assert s["next_close"].date() == datetime(2026, 4, 15).date()
