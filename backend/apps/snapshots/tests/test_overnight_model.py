import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.mark.django_db
def test_overnight_section_kind_allowed():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["overnight"])
    sec = SnapshotSection.objects.create(
        snapshot=snap, kind="overnight", payload={"ok": True}, status="done"
    )
    sec.full_clean()  # choices validation must pass
    assert sec.kind == "overnight"
