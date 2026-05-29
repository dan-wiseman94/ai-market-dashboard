import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.mark.django_db
def test_timeline_orders_and_computes_headline_delta():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])

    def mk(last):
        s = Snapshot.objects.create(
            profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA"
        )
        SnapshotSection.objects.create(
            snapshot=s, kind="quotes", status="done", payload={"NVDA": {"last": last}}
        )
        return s

    a, b = mk(100.0), mk(102.0)
    r = APIClient().get("/api/snapshots/timeline/?ticker=NVDA")
    assert r.status_code == 200
    rows = r.json()["results"]  # oldest -> newest
    assert [x["id"] for x in rows] == [a.id, b.id]
    assert rows[0]["headline_delta_pct"] is None  # oldest has no prior
    assert round(rows[1]["headline_delta_pct"], 4) == 2.0
