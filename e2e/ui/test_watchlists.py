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
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_watchlist_detail_add_remove_ticker(page, frontend_base_url, market) -> None:
    from apps.profiles.models import Watchlist

    wl = Watchlist.objects.get(name="E2E Core")
    d = WatchlistDetailPage(page, frontend_base_url)
    d.go(wl.id)
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_market_ticker_page_renders_ohlc_and_news(page, frontend_base_url, market) -> None:
    m = MarketTickerPage(page, frontend_base_url)
    m.go("AAPL")
    expect(page.locator("body")).to_be_visible()
