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
    d.expect_error_boundary_absent()
    expect(d.hero_heading).to_be_visible(timeout=10_000)
    expect(d.market_context_section).to_be_visible()
    expect(d.book_section).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_empty_state(page, frontend_base_url, minimal) -> None:
    """Fresh-ish DB — dashboard renders without an error boundary or stuck skeleton."""
    d = DashboardPage(page, frontend_base_url)
    d.go()
    d.expect_error_boundary_absent()
    expect(d.hero_heading).to_be_visible(timeout=10_000)
    expect(page.locator("[data-testid^='skeleton-']")).to_have_count(0)


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_cost_tile_reflects_airuns(page, frontend_base_url, analytics) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    d.expect_error_boundary_absent()
    cost_chip = page.get_by_title("Today's AI spend — click to see costs")
    expect(cost_chip).to_be_visible(timeout=10_000)
    expect(cost_chip).to_contain_text("$")
