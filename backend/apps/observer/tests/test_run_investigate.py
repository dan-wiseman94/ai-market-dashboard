from contextlib import ExitStack
from unittest.mock import patch

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import fire_observer
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


def _fire_plain(schedule, snap):
    """Fire fire_observer on the plain (non-structured/batch/consensus) path with
    capture/serialize/cost mocked; return the patched run_ai_on_message mock."""
    with ExitStack() as stack:
        for cm in (
            patch("apps.observer.services.run.any_market_open", return_value=True),
            patch("apps.observer.services.run.check_daily_cap"),
            patch("apps.observer.services.run.check_monthly_cap"),
            patch("apps.observer.services.run.capture", return_value=snap),
            patch("apps.observer.services.run.serialize_for_ai", return_value="## BODY"),
            patch("apps.observer.services.run.notify"),
        ):
            stack.enter_context(cm)
        run_ai = stack.enter_context(patch("apps.observer.services.run.run_ai_on_message"))
        fire_observer(schedule.id)
        return run_ai


@pytest.mark.django_db
def test_plain_observer_passes_investigate_flag():
    p = TradingProfile.objects.create(name="P", style="x")
    s = ObserverSchedule.objects.create(
        name="x",
        profile=p,
        market_hours_only=False,
        default_includes=["quotes"],
        investigate=True,
    )
    snap = Snapshot.objects.create(
        profile=p, includes=["quotes"], source="observer", status="ready"
    )
    run_ai = _fire_plain(s, snap)
    run_ai.delay.assert_called_once()
    assert run_ai.delay.call_args.kwargs["investigate"] is True


@pytest.mark.django_db
def test_plain_observer_default_not_investigate():
    p = TradingProfile.objects.create(name="P", style="x")
    s = ObserverSchedule.objects.create(
        name="x", profile=p, market_hours_only=False, default_includes=["quotes"]
    )
    snap = Snapshot.objects.create(
        profile=p, includes=["quotes"], source="observer", status="ready"
    )
    run_ai = _fire_plain(s, snap)
    assert run_ai.delay.call_args.kwargs["investigate"] is False
