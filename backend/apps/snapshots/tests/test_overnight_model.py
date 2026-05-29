import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializers import SnapshotListSerializer, SnapshotSerializer


@pytest.mark.django_db
def test_overnight_defaults_false_and_serializes():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=[])
    assert snap.overnight is False
    assert SnapshotSerializer(snap).data["overnight"] is False
    assert SnapshotListSerializer(snap).data["overnight"] is False


@pytest.mark.django_db
def test_overnight_section_kind_allowed():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["overnight"], overnight=True)
    sec = SnapshotSection.objects.create(
        snapshot=snap, kind="overnight", payload={"ok": True}, status="done"
    )
    sec.full_clean()  # choices validation must pass
    assert sec.kind == "overnight"
