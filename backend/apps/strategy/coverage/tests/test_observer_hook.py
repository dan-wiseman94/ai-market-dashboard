"""The observer keeps the house view current after a fire.

A covered ticker is revised; an uncovered one gets its first note while
auto-create is on, so the revision loop starts by itself on a newly watched name.
Either way it is bounded to the snapshot's primary ticker and best-effort
(suppressed at the observer call site).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.snapshots.models import Snapshot
from apps.strategy.coverage.hooks import maybe_revise_from_snapshot
from apps.strategy.models import CoverageNote
from apps.strategy.tasks import revise_from_observation

DELAY = "apps.strategy.tasks.revise_from_observation.delay"


@pytest.fixture
def ready_snapshot(db, profile) -> Snapshot:
    return Snapshot.objects.create(profile=profile, status="ready", primary_ticker="SPY")


def test_hook_dispatches_when_ticker_is_covered(ready_snapshot):
    CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(ready_snapshot)
    delay.assert_called_once_with("SPY", ready_snapshot.id)


def test_hook_opens_the_first_note_on_an_uncovered_ticker(ready_snapshot):
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(ready_snapshot)
    delay.assert_called_once_with("SPY", ready_snapshot.id)


@override_settings(COVERAGE_AUTO_CREATE_ENABLED=False)
def test_hook_noop_on_an_uncovered_ticker_when_auto_create_is_off(ready_snapshot):
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(ready_snapshot)
    delay.assert_not_called()


def test_hook_noop_when_no_primary_ticker(db, profile):
    snap = Snapshot.objects.create(profile=profile, status="ready")
    CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)
    with patch(DELAY) as delay:
        maybe_revise_from_snapshot(snap)
    delay.assert_not_called()


def test_task_invokes_service_with_snapshot_and_profile(ready_snapshot):
    with patch("apps.strategy.tasks.revise_coverage") as revise:
        revise_from_observation("SPY", ready_snapshot.id)
    revise.assert_called_once()
    args, kwargs = revise.call_args
    assert args[0] == "SPY"
    assert args[1].id == ready_snapshot.id
    assert kwargs["profile"].id == ready_snapshot.profile_id


def test_task_noop_when_snapshot_missing(db):
    with patch("apps.strategy.tasks.revise_coverage") as revise:
        revise_from_observation("SPY", 999_999)
    revise.assert_not_called()


def test_fire_observer_invokes_coverage_hook(db, profile):
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
        run_service.fire_observer(sched.id)

    hook.assert_called_once_with(snap)
