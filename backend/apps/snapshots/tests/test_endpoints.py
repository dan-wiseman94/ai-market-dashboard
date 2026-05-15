from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_snapshot_kicks_off_capture(api):
    p = TradingProfile.objects.create(name="P", style="x")
    with patch("apps.snapshots.views.capture_task.delay") as task:
        task.return_value.id = "task-1"
        resp = api.post(
            "/api/snapshots/",
            {
                "profile_id": p.id,
                "objective": "test",
                "includes": ["quotes"],
                "watchlist_tickers": ["SPY"],
            },
            format="json",
        )
    assert resp.status_code == 202
    body = resp.json()
    assert "id" in body
    assert body["status"] == "pending"


@pytest.mark.django_db
def test_get_snapshot_returns_with_sections(api):
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    SnapshotSection.objects.create(
        snapshot=s, kind="quotes", status="done", payload={"SPY": {"last": 1}}
    )
    r = api.get(f"/api/snapshots/{s.id}/")
    assert r.status_code == 200
    assert r.json()["sections"][0]["kind"] == "quotes"
