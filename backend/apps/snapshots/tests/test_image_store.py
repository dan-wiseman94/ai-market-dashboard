"""Image byte offload: new SnapshotImages store bytes on the /data volume,
not in Postgres; reads are disk-first with an in-DB fallback."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from apps.snapshots import image_store
from apps.snapshots.image_store import create_image, read_image_bytes, write_image_file
from apps.snapshots.models import SnapshotImage

PNG = b"\x89PNG\r\n\x1a\nDATA"


@pytest.fixture
def image_dir(tmp_path, settings):
    settings.SNAPSHOT_IMAGE_DIR = str(tmp_path / "images")
    return tmp_path / "images"


def test_write_image_file_writes_to_configured_dir(image_dir):
    path = write_image_file(PNG)
    p = Path(path)
    assert p.exists()
    assert p.parent == image_dir
    assert p.read_bytes() == PNG


@pytest.mark.django_db
def test_create_image_offloads_bytes_to_disk(image_dir):
    img = create_image(snapshot_id=None, kind="server_render", data=PNG, caption="c")
    assert img.file_path  # path recorded on the row
    assert img.data is None  # bytes are NOT in Postgres
    assert Path(img.file_path).exists()
    assert read_image_bytes(img) == PNG


@pytest.mark.django_db
def test_read_falls_back_to_in_db_bytes(image_dir):
    # An in-DB row: bytes in the BinaryField, no file_path.
    indb = SnapshotImage.objects.create(kind="client_capture", data=PNG, file_path="")
    assert read_image_bytes(indb) == PNG


@pytest.mark.django_db
def test_read_falls_back_when_file_path_missing_on_disk(image_dir):
    # file_path set but the file vanished -> fall back to in-DB bytes (defensive).
    img = SnapshotImage.objects.create(
        kind="server_render", data=PNG, file_path=str(image_dir / "gone.png")
    )
    assert read_image_bytes(img) == PNG


@pytest.mark.django_db
def test_create_image_falls_back_to_db_when_volume_unwritable(image_dir, monkeypatch):
    def _boom(*_a, **_k):
        raise OSError("read-only volume")

    monkeypatch.setattr(image_store, "write_image_file", _boom)
    img = create_image(snapshot_id=None, kind="server_render", data=PNG)
    assert img.file_path == ""  # nothing on disk
    assert bytes(img.data) == PNG  # bytes preserved in the DB rather than lost


@pytest.mark.django_db
def test_build_image_blocks_reads_offloaded_bytes(image_dir):
    """The AI payload path must base64 the on-disk bytes of an offloaded image."""
    from apps.snapshots.serializer import build_image_blocks

    img = create_image(snapshot_id=None, kind="server_render", data=PNG)
    blocks = build_image_blocks([img.id], provider_name="claude")
    assert len(blocks) == 1
    assert base64.b64encode(PNG).decode("ascii") in str(blocks[0])


@pytest.mark.django_db
def test_image_file_unlinked_on_row_delete(image_dir):
    img = create_image(snapshot_id=None, kind="server_render", data=PNG)
    path = Path(img.file_path)
    assert path.exists()
    img.delete()
    assert not path.exists()


@pytest.mark.django_db
def test_image_file_unlinked_on_queryset_delete(image_dir):
    # Connecting the post_delete signal must also disable fast-delete, so a
    # queryset .delete() (e.g. a Snapshot cascade) still unlinks each file.
    img = create_image(snapshot_id=None, kind="server_render", data=PNG)
    path = Path(img.file_path)
    assert path.exists()
    SnapshotImage.objects.filter(id=img.id).delete()
    assert not path.exists()


@pytest.mark.django_db
def test_in_db_row_delete_is_safe(image_dir):
    # An in-DB row (bytes in DB, no file_path) deletes without trying to unlink.
    indb = SnapshotImage.objects.create(kind="client_capture", data=PNG, file_path="")
    indb.delete()  # must not raise
