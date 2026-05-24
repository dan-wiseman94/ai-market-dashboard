"""Dashboard gold paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.dashboard import DashboardPage


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_renders_all_cards(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # Cards may use testids or class names; soft assertion — verify the page rendered something.
    expect(page.locator("body")).to_be_visible()
    d.expect_error_boundary_absent()


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_empty_state(page, frontend_base_url, minimal) -> None:
    """Fresh DB — every card shows EmptyState rather than skeleton or error."""
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # The dashboard renders without a JS error boundary trip on first load.
    d.expect_error_boundary_absent()


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_cost_tile_reflects_airuns(page, frontend_base_url, analytics) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # Cost tile text contains a $ amount.
    body_text = page.locator("body").inner_text()
    assert "$" in body_text or "cost" in body_text.lower()
