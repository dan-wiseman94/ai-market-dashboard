"""Diff-mode prior-snapshot lookup contract.

`_build_payload_text` must order Snapshots by ``captured_at`` (Snapshot's
timestamp field). ``created_at`` is not a Snapshot field — ordering by it
raises ``FieldError`` at runtime on every diff-mode fire. This pins the
behavior.
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

    # Ordering by created_at would raise FieldError("Cannot resolve keyword 'created_at'").
    text = _build_payload_text(sched, curr, "claude", "claude-sonnet-4-6")

    assert f"Delta since snapshot #{prev.id}" in text
    assert "watch NVDA" in text
