from unittest.mock import patch

import pytest
from freezegun import freeze_time

from apps.observer.models import ObserverSchedule
from apps.observer.services.close_relative import fire_due_close_relative
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
@freeze_time("2026-11-27 17:55:30")  # 5m before the 13:00 ET (18:00 UTC) half-day close
def test_fires_in_window_then_guards_same_day():
    profile = TradingProfile.objects.create(name="p", style="s")
    sched = ObserverSchedule.objects.create(
        name="eod",
        profile=profile,
        fire_mode="relative_to_close",
        close_offset_minutes=5,
        default_watchlist_tickers=["SPY"],
    )
    with patch("apps.observer.tasks.run_observer_task.delay") as delay:
        out = fire_due_close_relative()
        assert out["fired"] == 1
        delay.assert_called_once_with(schedule_id=sched.id)
        # second tick same minute -> guarded
        out2 = fire_due_close_relative()
        assert out2["fired"] == 0


@pytest.mark.django_db
@freeze_time("2026-11-27 15:00:00")  # well before the early close window
def test_does_not_fire_outside_window():
    profile = TradingProfile.objects.create(name="p", style="s")
    ObserverSchedule.objects.create(
        name="eod",
        profile=profile,
        fire_mode="relative_to_close",
        close_offset_minutes=5,
        default_watchlist_tickers=["SPY"],
    )
    with patch("apps.observer.tasks.run_observer_task.delay") as delay:
        assert fire_due_close_relative()["fired"] == 0
        delay.assert_not_called()
