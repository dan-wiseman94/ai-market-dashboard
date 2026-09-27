import pytest

from apps.snapshots.models import SnapshotImage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal valid PNG header


@pytest.mark.django_db
def test_snapshotimage_can_be_staged_without_snapshot():
    img = SnapshotImage.objects.create(
        snapshot=None,
        kind="client_capture",
        data=PNG_BYTES,
    )
    assert img.snapshot is None
