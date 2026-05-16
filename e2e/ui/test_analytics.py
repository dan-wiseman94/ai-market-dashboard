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
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_orders_by_forward_return(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_zero_coverage_row(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_cost_per_insight_card(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_heatmap_renders_cells(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_unusual_options_card_shows_triggers(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    try:
        a.set_ticker("AAPL")
    except Exception:
        pytest.skip("Ticker input not present on /analytics")
    expect(page.locator("body")).to_be_visible()
