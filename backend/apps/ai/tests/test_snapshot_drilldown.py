# backend/apps/costs/tests/test_snapshot_drilldown.py
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.ai.cost_reporting import snapshot_breakdown
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import AIRun, Message, Thread


def _make_profile():
    return TradingProfile.objects.create(name="P", style="test style")


@pytest.mark.django_db
def test_snapshot_breakdown_proportional_attribution() -> None:
    profile = _make_profile()
    snap = Snapshot.objects.create(profile=profile)
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", payload={}, status="done", payload_tokens=700
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="news", payload={}, status="done", payload_tokens=300
    )

    t = Thread.objects.create(kind="consult", title="t", pinned_snapshot_id=snap.id)
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="done")
    AIRun.objects.create(
        message=m,
        provider="claude",
        model="m",
        cost_usd=Decimal("0.1000"),
        input_tokens=1000,
        output_tokens=0,
        cached_tokens=0,
        latency_ms=1,
        status="done",
    )

    rows = snapshot_breakdown(snap.id)
    by_kind = {r["section"]: r for r in rows}
    assert by_kind["quotes"]["payload_tokens"] == 700
    assert by_kind["quotes"]["cost_share_usd"] == Decimal("0.0700")
    assert by_kind["news"]["cost_share_usd"] == Decimal("0.0300")


@pytest.mark.django_db
def test_snapshot_breakdown_no_ai_run_returns_zero_cost() -> None:
    profile = _make_profile()
    snap = Snapshot.objects.create(profile=profile)
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", payload={}, status="done", payload_tokens=100
    )
    rows = snapshot_breakdown(snap.id)
    assert rows[0]["payload_tokens"] == 100
    assert rows[0]["cost_share_usd"] == Decimal("0")
