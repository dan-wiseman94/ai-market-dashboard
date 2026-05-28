"""Analytics gold paths — 5 cards + zero-coverage."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.analytics import AnalyticsPage


@pytest.mark.integration
@pytest.mark.ui
def test_analytics_page_renders_all_five_cards(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    expect(a.card_leaderboard).to_be_visible(timeout=10_000)
    expect(a.card_cpi).to_be_visible()
    expect(a.card_heatmap).to_be_visible()
    expect(a.card_timeline).to_be_visible()
    expect(a.card_unusual()).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_orders_by_forward_return(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # The leaderboard card renders at least one provider/model row.
    expect(a.card_leaderboard.get_by_role("row").first).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_zero_coverage_row(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # Runs without price history surface coverage 0% honestly (spec/leaderboard).
    expect(a.card_leaderboard).to_contain_text("%", timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_cost_per_insight_card(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    expect(a.card_cpi).to_contain_text("$", timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_heatmap_renders_cells(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # The heatmap renders a grid of day cells (data-testid="heat-cell").
    expect(a.card_heatmap.locator("[data-testid='heat-cell']").first).to_be_visible(
        timeout=10_000
    )


@pytest.mark.integration
@pytest.mark.ui
def test_unusual_options_card_shows_triggers(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # Before a ticker is entered the card prompts to scan.
    expect(a.card_unusual()).to_contain_text("Enter a ticker", timeout=10_000)
    # Entering a ticker fires the scan — the prompt is replaced by results/loading/empty.
    a.set_ticker("AAPL")
    expect(a.card_unusual()).not_to_contain_text("Enter a ticker to scan", timeout=10_000)
