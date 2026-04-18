from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from apps.observer.services.market_hours import is_market_open, market_status


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET → market open
def test_is_market_open_during_session():
    assert is_market_open() is True


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_is_market_open_returns_false_on_weekend():
    assert is_market_open() is False


@freeze_time("2026-07-04 14:00:00")  # July 4 (US holiday — but a Saturday in 2026; observed on Friday)
def test_is_market_open_returns_false_on_holiday():
    # July 4 2026 is a Saturday — markets closed for weekend regardless of holiday observance.
    assert is_market_open() is False


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET
def test_market_status_returns_open_during_session():
    s = market_status()
    assert s["is_open"] is True
    assert s["next_close"] is not None
    assert s["next_close"].date() == datetime(2026, 4, 15).date()


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_market_status_off_hours_has_next_open():
    s = market_status()
    assert s["is_open"] is False
    assert s["next_open"] is not None
