import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.mark.django_db
def test_create_snapshot_with_sections():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(
        profile=p,
        objective="Looking for long entry on NVDA",
        includes=["quotes", "positions"],
        source="manual",
    )
    assert s.status == "pending"
    assert s.captured_at is not None

    SnapshotSection.objects.create(
        snapshot=s, kind="quotes", payload={"SPY": {"last": 550}}, status="done"
    )
    SnapshotSection.objects.create(
        snapshot=s, kind="positions", payload=[], status="failed", error="network"
    )
    assert s.sections.count() == 2


@pytest.mark.django_db
def test_snapshot_finalizes_when_all_sections_done():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, objective="", includes=["quotes"], source="manual")

    s.status = "ready"
    s.save()
    s.refresh_from_db()
    assert s.status == "ready"


@pytest.mark.django_db
def test_section_kind_choices():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual")
    for kind in ["quotes", "ohlc", "positions", "breadth", "notes"]:
        SnapshotSection.objects.create(snapshot=s, kind=kind, payload={}, status="done")
    assert s.sections.count() == 5
