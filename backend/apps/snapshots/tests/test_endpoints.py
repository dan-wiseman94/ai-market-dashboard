import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


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
