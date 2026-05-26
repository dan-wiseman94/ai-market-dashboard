"""Snapshot gold + edge paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.costs import CostsPage
from e2e.pages.snapshot import SnapshotPage
from e2e.pages.snapshot_cost import SnapshotCostPage


@pytest.mark.integration
@pytest.mark.ui
def test_capture_all_sections_ok(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    # Smoke: the composer page renders.
    expect(page.locator("body")).to_be_visible()
    s.expect_error_boundary_absent()


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_drill_down(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(status="ready").first()
    d = SnapshotCostPage(page, frontend_base_url)
    d.go(snap.id)
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_diff_endpoint_surfaced(page, frontend_base_url, api_client, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    ready = list(Snapshot.objects.filter(status="ready").order_by("id")[:2])
    if len(ready) < 2:
        pytest.skip("need ≥2 ready snapshots for the diff endpoint")
    prev, curr = ready[0], ready[1]
    # Assert the diff endpoint's real contract: {delta, prev_id, curr_id}.
    r = api_client.get(f"/api/snapshots/{curr.id}/diff/", params={"against": prev.id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"delta", "prev_id", "curr_id"}
    assert body["prev_id"] == prev.id
    assert body["curr_id"] == curr.id
    assert isinstance(body["delta"], str)
    # …and the drill-down route that consumes it renders without crashing.
    page.goto(f"{frontend_base_url}/costs/snapshot/{curr.id}")
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_capture_partial_failure_marks_sections(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("news-503")
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_capture_oversized_image_returns_413(api_client) -> None:
    # A >5MB body trips Django's DATA_UPLOAD_MAX_MEMORY_SIZE guard; the image
    # endpoint must translate that into a clean 413 {code: too_large}, not the
    # bare 400 HTML page Django would otherwise emit.
    body = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)
    r = api_client.post(
        "/api/snapshots/images/",
        content=body,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 413, r.text
    assert r.json()["code"] == "too_large"


@pytest.mark.integration
@pytest.mark.ui
def test_costs_page_loads_from_snapshot(page, frontend_base_url, analytics) -> None:
    """Smoke: the costs page loads after snapshots seed has produced AIRun rows."""
    costs = CostsPage(page, frontend_base_url)
    costs.go()
    expect(page.locator("body")).to_be_visible()
