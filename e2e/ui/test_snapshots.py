"""Snapshot gold + edge paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.waits import wait_for_app_ready
from e2e.pages.costs import CostsPage
from e2e.pages.snapshot import SnapshotPage
from e2e.pages.snapshot_cost import SnapshotCostPage


@pytest.mark.integration
@pytest.mark.ui
def test_capture_all_sections_ok(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    # The capture button is present (gated on profileId being selected).
    expect(s.capture_btn).to_be_visible(timeout=10_000)
    # The Profile label + select renders (label text is visible even without htmlFor).
    expect(page.get_by_text("Profile", exact=False).first).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_drill_down(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(status="ready").first()
    d = SnapshotCostPage(page, frontend_base_url)
    d.go(snap.id)
    d.expect_error_boundary_absent()
    expect(page.get_by_role("heading", level=1)).to_contain_text(str(snap.id), timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_diff_endpoint_surfaced(page, frontend_base_url, api_client, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    # The snapshots seed creates four ready snapshots, so two always exist.
    ready = list(Snapshot.objects.filter(status="ready").order_by("id")[:2])
    assert len(ready) >= 2, "snapshots seed must provide ≥2 ready snapshots"
    prev, curr = ready[0], ready[1]
    r = api_client.get(f"/api/snapshots/{curr.id}/diff/", params={"against": prev.id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"delta", "prev_id", "curr_id"}
    assert body["prev_id"] == prev.id
    assert body["curr_id"] == curr.id
    assert isinstance(body["delta"], str)
    page.goto(f"{frontend_base_url}/costs/snapshot/{curr.id}")
    wait_for_app_ready(page)
    expect(page.get_by_text("Something went wrong", exact=False)).to_have_count(0)
    expect(page.get_by_role("heading", level=1)).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_capture_partial_failure_marks_sections(api_client, minimal, scenario) -> None:
    """Under news-503 the finnhub-backed news section fails while the schwab-backed
    quotes section still succeeds — a genuine partial failure.

    Exercises the whole path: X-E2E-Scenario header → ScenarioHeaderMiddleware →
    capture view → capture_task scenario propagation into the worker → per-section
    failure. (Before this was wired, news-503 was inert and this test asserted only
    that the page rendered.)
    """
    import time

    from apps.profiles.models import TradingProfile

    scenario.use("news-503")
    profile = TradingProfile.objects.first()
    assert profile is not None

    r = api_client.post(
        "/api/snapshots/",
        json={
            "profile_id": profile.id,
            "objective": "partial-failure probe",
            "includes": ["quotes", "news"],
            "watchlist_tickers": ["SPY"],
        },
    )
    assert r.status_code == 202, r.text
    snap_id = r.json()["id"]

    # Capture runs in the worker; poll the detail endpoint until it settles.
    sections: dict[str, str] = {}
    for _ in range(30):
        body = api_client.get(f"/api/snapshots/{snap_id}/").json()
        if body["status"] != "pending":
            sections = {s["kind"]: s["status"] for s in body["sections"]}
            break
        time.sleep(1)

    assert sections.get("news") == "failed", sections
    assert sections.get("quotes") == "done", sections


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
    """Costs page loads and shows a dollar figure after analytics seed produces AIRun rows."""
    costs = CostsPage(page, frontend_base_url)
    costs.go()
    costs.expect_error_boundary_absent()
    expect(costs.today_tile).to_be_visible(timeout=10_000)
    expect(costs.today_tile).to_contain_text("$")
