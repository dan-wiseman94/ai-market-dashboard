# backend/apps/export/tests/test_serialize_snapshot.py
from __future__ import annotations

import pytest

from apps.export.serializers import snapshot_images, snapshot_to_json, snapshot_to_markdown


@pytest.mark.django_db
def test_snapshot_json_shape() -> None:
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotSection

    prof = TradingProfile.objects.create(name="p", style="swing")
    snap = Snapshot.objects.create(profile=prof)
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", payload={"AAPL": 1.0}, status="done"
    )
    out = snapshot_to_json(snap)
    assert out["id"] == snap.id
    assert out["sections"][0]["kind"] == "quotes"
    assert out["sections"][0]["payload"] == {"AAPL": 1.0}


@pytest.mark.django_db
def test_snapshot_markdown_renders_sections() -> None:
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotSection

    prof = TradingProfile.objects.create(name="p2", style="momentum")
    snap = Snapshot.objects.create(profile=prof)
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", payload={"AAPL": 1.0}, status="done"
    )
    md = snapshot_to_markdown(snap)
    assert "# Snapshot" in md
    assert "## quotes" in md


@pytest.mark.django_db
def test_snapshot_images_streams_bytes() -> None:
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotImage

    prof = TradingProfile.objects.create(name="p3", style="scalp")
    snap = Snapshot.objects.create(profile=prof)
    SnapshotImage.objects.create(
        snapshot=snap,
        kind="server_render",
        data=b"\x89PNG\r\n\x1a\n" + b"x" * 100,
    )
    images = list(snapshot_images(snap))
    assert len(images) == 1
    name, data = images[0]
    assert name.endswith(".png")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.django_db
def test_snapshot_images_reads_disk_offloaded_bytes(tmp_path) -> None:
    """Disk-offloaded images (data=NULL, file_path set — the default from
    image_store.create_image) must export their real bytes via read_image_bytes.
    bytes(img.data) would be bytes(None) -> TypeError, silently breaking export of
    every snapshot with offloaded images."""
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotImage

    prof = TradingProfile.objects.create(name="p4", style="swing")
    snap = Snapshot.objects.create(profile=prof)
    png = b"\x89PNG\r\n\x1a\n" + b"y" * 50
    f = tmp_path / "render.png"
    f.write_bytes(png)
    SnapshotImage.objects.create(snapshot=snap, kind="server_render", data=None, file_path=str(f))

    images = list(snapshot_images(snap))

    assert len(images) == 1
    _, data = images[0]
    assert data == png
