import pytest

from apps.snapshots.image_store import read_image_bytes
from apps.snapshots.models import SnapshotImage

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
NOT_PNG = b"GIF89a" + b"\x00" * 50


@pytest.mark.django_db
def test_upload_staged_image_persists_with_null_snapshot(api):
    resp = api.post(
        "/api/snapshots/images/?staged=true",
        data=PNG_BYTES,
        content_type="image/png",
        HTTP_X_CAPTION="SPY 5m",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    img = SnapshotImage.objects.get(id=body["id"])
    assert img.snapshot is None
    assert img.kind == "client_capture"
    assert img.caption == "SPY 5m"
    # C7: bytes are offloaded to the /data volume (data=None on disk-write success),
    # so read through the disk-first helper rather than the raw BinaryField.
    assert read_image_bytes(img).startswith(b"\x89PNG")


@pytest.mark.django_db
def test_upload_invalid_png_returns_400(api):
    resp = api.post(
        "/api/snapshots/images/?staged=true",
        data=NOT_PNG,
        content_type="image/png",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_png"


@pytest.mark.django_db
def test_list_staged_returns_only_unattached(api):
    SnapshotImage.objects.create(snapshot=None, kind="client_capture", data=PNG_BYTES)
    resp = api.get("/api/snapshots/images/?staged=true")
    assert resp.status_code == 200
    assert len(resp.json()["images"]) == 1


@pytest.mark.django_db
def test_serve_image_returns_bytes(api):
    img = SnapshotImage.objects.create(snapshot=None, kind="client_capture", data=PNG_BYTES)
    resp = api.get(f"/api/snapshots/images/{img.id}/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")
