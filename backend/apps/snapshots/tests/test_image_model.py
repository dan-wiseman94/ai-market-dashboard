import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal valid PNG header


@pytest.mark.django_db
def test_snapshotimage_attached_to_snapshot():
    profile = TradingProfile.objects.create(name="Default", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["image"])
    img = SnapshotImage.objects.create(
        snapshot=snap,
        kind="client_capture",
        data=PNG_BYTES,
        caption="SPY 5m",
    )
    assert img.id is not None
    assert bytes(img.data).startswith(b"\x89PNG")
    assert img.snapshot_id == snap.id


@pytest.mark.django_db
def test_snapshotimage_can_be_staged_without_snapshot():
    img = SnapshotImage.objects.create(
        snapshot=None,
        kind="client_capture",
        data=PNG_BYTES,
    )
    assert img.snapshot is None
