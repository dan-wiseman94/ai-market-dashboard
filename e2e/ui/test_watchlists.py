"""Watchlists + market-ticker gold paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.market_ticker import MarketTickerPage
from e2e.pages.watchlist_detail import WatchlistDetailPage
from e2e.pages.watchlists import WatchlistsPage


@pytest.mark.integration
@pytest.mark.ui
def test_watchlists_list_and_create(page, frontend_base_url, market) -> None:
    w = WatchlistsPage(page, frontend_base_url)
    w.go()
    w.expect_error_boundary_absent()
    w.create("E2E Created WL")
    expect(w.list_item("E2E Created WL")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_watchlist_detail_add_remove_ticker(page, frontend_base_url, market) -> None:
    from apps.profiles.models import Watchlist

    wl = Watchlist.objects.get(name="E2E Core")
    d = WatchlistDetailPage(page, frontend_base_url)
    d.go(wl.id)
    d.expect_error_boundary_absent()
    # The detail page shows the watchlist's name as a heading.
    expect(page.get_by_role("heading", name="E2E Core")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_market_ticker_page_renders_ohlc_and_news(page, frontend_base_url, market) -> None:
    m = MarketTickerPage(page, frontend_base_url)
    m.go("AAPL")
    m.expect_error_boundary_absent()
    expect(m.ohlc_chart).to_be_visible(timeout=10_000)
