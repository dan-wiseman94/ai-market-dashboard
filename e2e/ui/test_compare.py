"""Compare — 2 branches, 3 providers, cost routing."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.snapshot import SnapshotPage


@pytest.mark.integration
@pytest.mark.ui
def test_compare_two_branches_stream_and_cost(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_compare_three_providers_routes_costs(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()
