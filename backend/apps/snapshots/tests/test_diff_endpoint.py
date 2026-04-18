"""GET /api/snapshots/<id>/diff/?against=<other_id> returns the delta."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def profile(db):
    from apps.profiles.models import TradingProfile
    return TradingProfile.objects.create(name="p", style="s")


@pytest.fixture
def two_snapshots(db, profile):
    from apps.snapshots.models import Snapshot, SnapshotSection
    prev = Snapshot.objects.create(profile=profile, status="ready", source="manual")
    SnapshotSection.objects.create(
        snapshot=prev, kind="quotes", status="done",
        payload={"SPY": {"last": 520.0}, "QQQ": {"last": 440.0}},
    )
    curr = Snapshot.objects.create(profile=profile, status="ready", source="manual")
    SnapshotSection.objects.create(
        snapshot=curr, kind="quotes", status="done",
        payload={"SPY": {"last": 525.0}, "QQQ": {"last": 440.5}},
    )
    return prev, curr


def test_snapshot_diff_endpoint_returns_markdown(db, two_snapshots) -> None:
    prev, curr = two_snapshots
    client = APIClient()
    resp = client.get(f"/api/snapshots/{curr.id}/diff/?against={prev.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "delta" in body
    assert "SPY" in body["delta"]
    assert body["prev_id"] == prev.id
    assert body["curr_id"] == curr.id


def test_snapshot_diff_missing_against_400(db, two_snapshots) -> None:
    _, curr = two_snapshots
    client = APIClient()
    resp = client.get(f"/api/snapshots/{curr.id}/diff/")
    assert resp.status_code == 400


def test_snapshot_diff_unknown_id_404(db, two_snapshots) -> None:
    _, curr = two_snapshots
    client = APIClient()
    resp = client.get(f"/api/snapshots/{curr.id}/diff/?against=999999")
    assert resp.status_code == 404
