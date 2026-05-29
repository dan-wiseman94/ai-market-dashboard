import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.fixture
def snaps(db):
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    a = Snapshot.objects.create(
        profile=p,
        objective="A",
        includes=["quotes"],
        status="ready",
        source="manual",
        primary_ticker="NVDA",
    )
    SnapshotSection.objects.create(
        snapshot=a, kind="quotes", status="done", payload={"NVDA": {"last": 1}}
    )
    b = Snapshot.objects.create(
        profile=p,
        objective="B",
        includes=["news"],
        status="ready",
        source="observer",
        primary_ticker="SPY",
    )
    return p, a, b


def test_list_omits_payloads_and_includes_summary(snaps):
    _, a, _ = snaps
    r = APIClient().get("/api/snapshots/")
    assert r.status_code == 200
    row = next(x for x in r.json()["results"] if x["id"] == a.id)
    assert row["primary_ticker"] == "NVDA"
    assert row["section_kinds"] == ["quotes"]
    assert "sections" not in row  # the heavy section payloads are not serialized into the list


def test_list_filters_by_ticker_and_source(snaps):
    _, a, b = snaps
    r = APIClient().get("/api/snapshots/?ticker=nvda")
    ids = [x["id"] for x in r.json()["results"]]
    assert ids == [a.id]
    r2 = APIClient().get("/api/snapshots/?source=observer")
    assert [x["id"] for x in r2.json()["results"]] == [b.id]
