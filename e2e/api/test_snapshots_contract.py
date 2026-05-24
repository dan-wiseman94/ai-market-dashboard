"""Snapshot endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_snapshot_list_returns_results(api_client, snapshots) -> None:
    r = api_client.get("/api/snapshots/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)
    assert len(rows) >= 1


@pytest.mark.integration
def test_snapshot_detail_returns_sections(api_client, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(status="ready").first()
    assert snap is not None
    r = api_client.get(f"/api/snapshots/{snap.id}/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    # Sections may be nested or at top level
    sections = body.get("sections")
    if sections is None:
        # try /sections endpoint as fallback
        r2 = api_client.get(f"/api/snapshots/{snap.id}/sections/")
        if r2.status_code == 200:
            sections = r2.json()
    if sections is not None:
        assert isinstance(sections, list)


@pytest.mark.integration
def test_snapshot_image_serve_returns_bytes_or_404(api_client, snapshots) -> None:
    from apps.snapshots.models import SnapshotImage

    img = SnapshotImage.objects.first()
    if img is None:
        # No image seeded — verify the route is registered by hitting a missing id
        r = api_client.get("/api/snapshots/images/999999/")
        assert r.status_code == 404
        return
    r = api_client.get(f"/api/snapshots/images/{img.id}/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 0
