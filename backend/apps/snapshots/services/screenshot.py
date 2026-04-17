"""Client-side screenshot upload + validation."""
from __future__ import annotations

from apps.snapshots.models import SnapshotImage

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 5 * 1024 * 1024


class InvalidPNGError(ValueError):
    pass


class ImageTooLargeError(ValueError):
    pass


def attach_client_image(
    snapshot_id: int | None, png_bytes: bytes, caption: str = "",
) -> SnapshotImage:
    if not png_bytes.startswith(PNG_MAGIC):
        raise InvalidPNGError("data does not start with PNG magic bytes")
    if len(png_bytes) > MAX_BYTES:
        raise ImageTooLargeError(f"image exceeds {MAX_BYTES} bytes")
    return SnapshotImage.objects.create(
        snapshot_id=snapshot_id, kind="client_capture",
        data=png_bytes, caption=caption[:256],
    )
