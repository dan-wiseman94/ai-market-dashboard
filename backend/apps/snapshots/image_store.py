"""Snapshot image byte storage (C7).

Image bytes used to live in Postgres (`SnapshotImage.data`, a BinaryField),
which bloated every ``pg_dump``. New images are written to the ``/data`` volume
instead and the row stores only a ``file_path`` (bytes column NULL). Reads are
disk-first with a fallback to the legacy BinaryField, so pre-existing rows keep
working untouched — no data migration, fully reversible.

Backup story: the DB dump no longer carries image bytes; the images live on the
persistent ``app_data:/data`` volume (which is part of the deployment's backup
surface, like any blob store). Restore = DB restore + that volume.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings


def image_dir() -> Path:
    d = Path(getattr(settings, "SNAPSHOT_IMAGE_DIR", "/data/images"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_image_file(data: bytes, *, ext: str = "png") -> str:
    """Write image bytes to the volume under a unique name; return the abs path."""
    path = image_dir() / f"{uuid.uuid4().hex}.{ext}"
    path.write_bytes(data)
    return str(path)


def read_image_bytes(img) -> bytes:
    """Bytes for a SnapshotImage: from disk when ``file_path`` is set and the
    file exists, else the legacy in-DB ``data`` (or empty when neither)."""
    fp = getattr(img, "file_path", "") or ""
    if fp:
        p = Path(fp)
        if p.exists():
            return p.read_bytes()
    return bytes(img.data) if img.data else b""


def create_image(*, snapshot_id, kind: str, data: bytes, caption: str = "", **extra):
    """Create a SnapshotImage with its bytes offloaded to the /data volume.

    Writes the bytes to disk and stores only the path (``data`` NULL), so the row
    stays tiny in pg_dump. Falls back to in-DB bytes if the volume write fails so
    a capture never silently loses its image.
    """
    from apps.snapshots.models import SnapshotImage

    try:
        file_path = write_image_file(data)
        return SnapshotImage.objects.create(
            snapshot_id=snapshot_id,
            kind=kind,
            data=None,
            file_path=file_path,
            caption=caption,
            **extra,
        )
    except OSError:
        # Volume not writable (misconfig) — degrade to the legacy in-DB path
        # rather than dropping the image.
        return SnapshotImage.objects.create(
            snapshot_id=snapshot_id, kind=kind, data=data, caption=caption, **extra
        )
