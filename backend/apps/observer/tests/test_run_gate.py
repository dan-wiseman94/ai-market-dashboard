from unittest.mock import patch

import pytest
from freezegun import freeze_time

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import run_observer
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_skips_when_all_watched_markets_closed():
    profile = TradingProfile.objects.create(name="p", style="s")
    sched = ObserverSchedule.objects.create(
        name="eq",
        profile=profile,
        market_hours_only=True,
        default_watchlist_tickers=["SPY"],
    )
    with patch("apps.observer.services.run.capture") as cap:
        assert run_observer(sched.id) is None
        cap.assert_not_called()


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday — crypto open
def test_proceeds_when_a_watched_market_open():
    profile = TradingProfile.objects.create(name="p", style="s")
    sched = ObserverSchedule.objects.create(
        name="cx",
        profile=profile,
        market_hours_only=True,
        default_watchlist_tickers=["BTC-USD"],
        default_includes=[],
    )
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    with (
        patch("apps.observer.services.run.capture", return_value=snap) as cap,
        patch("apps.observer.services.run.run_ai_on_message"),
    ):
        run_observer(sched.id)
        cap.assert_called_once()
