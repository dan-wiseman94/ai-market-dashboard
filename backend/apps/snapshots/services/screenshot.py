"""Client-side screenshot upload + validation."""

from __future__ import annotations

from django.conf import settings

from apps.snapshots.image_store import create_image
from apps.snapshots.models import SnapshotImage

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# The upload cap has one knob: Django's body-buffer guard. This validator must agree
# with it — a larger value here is unreachable (Django rejects the body first) and a
# smaller one splits the limit across two constants.
MAX_BYTES = settings.DATA_UPLOAD_MAX_MEMORY_SIZE


class InvalidPNGError(ValueError):
    pass


class ImageTooLargeError(ValueError):
    pass


def attach_client_image(
    snapshot_id: int | None,
    png_bytes: bytes,
    caption: str = "",
) -> SnapshotImage:
    if not png_bytes.startswith(PNG_MAGIC):
        raise InvalidPNGError("data does not start with PNG magic bytes")
    if len(png_bytes) > MAX_BYTES:
        raise ImageTooLargeError(f"image exceeds {MAX_BYTES} bytes")
    return create_image(
        snapshot_id=snapshot_id,
        kind="client_capture",
        data=png_bytes,
        caption=caption[:256],
    )
