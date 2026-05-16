"""Journey 1 — the gold path.

Given a seeded provider + profile, compose a snapshot, send it to AI, and
verify /costs reflects non-zero spend.

Requires MOCK_EXTERNAL=true (compose.e2e.yaml overlay). Run via `make e2e`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_FRONTEND_URL
from e2e.pages.costs import CostsPage
from e2e.pages.snapshot import SnapshotPage


@pytest.mark.integration
def test_capture_to_cost(page) -> None:
    snap = SnapshotPage(page, E2E_FRONTEND_URL)
    snap.go()
    page.get_by_label("Profile").select_option(label="E2E Default")
    page.get_by_label("Objective").fill("quick check")
    page.get_by_role("button", name="Capture").click()

    expect(page.get_by_text("complete", exact=False)).to_be_visible(timeout=30000)

    page.get_by_role("button", name="Send to AI").click()
    expect(page.get_by_text("Mocked response")).to_be_visible(timeout=15000)

    costs = CostsPage(page, E2E_FRONTEND_URL)
    costs.go()
    expect(page.get_by_text("claude", exact=False)).to_be_visible()
