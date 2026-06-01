"""The observer auto-revises a covered ticker's house view after a fire (M14 F3).

The hook is *opt-in by virtue of the CoverageNote already existing* — you opt in
by covering a name. It is bounded to the snapshot's primary ticker and is
best-effort (suppressed at the observer call site).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.coverage.hooks import maybe_revise_from_snapshot
from apps.coverage.models import CoverageNote
from apps.coverage.tasks import revise_from_observation
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot

DELAY = "apps.coverage.tasks.revise_from_observation.delay"


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s", default_provider="claude")


@pytest.fixture
def ready_snapshot(db, profile) -> Snapshot:
    return Snapshot.objects.create(profile=profile, status="ready", primary_ticker="SPY")


def test_hook_dispatches_when_ticker_is_covered(ready_snapshot):
    CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(ready_snapshot)
    delay.assert_called_once_with("SPY", ready_snapshot.id)


def test_hook_noop_when_ticker_not_covered(ready_snapshot):
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(ready_snapshot)
    delay.assert_not_called()


def test_hook_noop_when_no_primary_ticker(db, profile):
    snap = Snapshot.objects.create(profile=profile, status="ready")  # primary_ticker is None
    CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(snap)
    delay.assert_not_called()


def test_task_invokes_service_with_snapshot_and_profile(ready_snapshot):
    with patch("apps.coverage.tasks.revise_coverage") as revise:
        revise_from_observation("SPY", ready_snapshot.id)
    revise.assert_called_once()
    args, kwargs = revise.call_args
    assert args[0] == "SPY"
    assert args[1].id == ready_snapshot.id
    assert kwargs["profile"].id == ready_snapshot.profile_id


def test_task_noop_when_snapshot_missing(db):
    with patch("apps.coverage.tasks.revise_coverage") as revise:
        revise_from_observation("SPY", 999_999)
    revise.assert_not_called()


def test_run_observer_invokes_coverage_hook(db, profile):
    from apps.observer.models import ObserverSchedule
    from apps.observer.services import run as run_service

    sched = ObserverSchedule.objects.create(
        name="s", profile=profile, objective_template="watch", market_hours_only=False
    )
    snap = Snapshot.objects.create(profile=profile, status="ready", primary_ticker="SPY")

    with (
        patch.object(run_service, "capture", return_value=snap),
        patch.object(run_service.run_ai_on_message, "delay"),
        patch("apps.observer.services.run.maybe_revise_from_snapshot") as hook,
    ):
        run_service.run_observer(sched.id)

    hook.assert_called_once_with(snap)
