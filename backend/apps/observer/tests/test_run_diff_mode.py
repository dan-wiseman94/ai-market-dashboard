"""Regression test for the diff-mode prior-snapshot lookup.

`_build_payload_text` ordered Snapshots by a non-existent ``created_at`` field,
which raises ``FieldError`` at runtime on every diff-mode fire (Snapshot's
timestamp is ``captured_at``). mypy + django-stubs surfaced it; this locks the
behavior. Diff-mode had no test, which is why the bug shipped.
"""

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import _build_payload_text
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


def _ready_snap(profile: TradingProfile, last: float) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"NVDA": {"last": last}}
    )
    return snap


@pytest.mark.django_db
def test_build_payload_text_diff_mode_finds_prior_snapshot():
    profile = TradingProfile.objects.create(name="diff-prof", default_includes=["quotes"])
    sched = ObserverSchedule.objects.create(
        name="diff-sched",
        profile=profile,
        objective_template="watch NVDA",
        mode="diff",
    )
    prev = _ready_snap(profile, 100)
    curr = _ready_snap(profile, 110)

    # Before the fix this raised FieldError("Cannot resolve keyword 'created_at'").
    text = _build_payload_text(sched, curr, "claude", "claude-sonnet-4-6")

    assert f"Delta since snapshot #{prev.id}" in text
    assert "watch NVDA" in text
