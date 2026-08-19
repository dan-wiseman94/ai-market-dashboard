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
    import uuid

    # Unique name: the e2e DB is shared and not rolled back, so a fixed name
    # would collide with a prior run (duplicate-name create is a no-op).
    name = f"E2E WL {uuid.uuid4().hex[:8]}"
    w = WatchlistsPage(page, frontend_base_url)
    w.go()
    w.expect_error_boundary_absent()
    w.create(name)
    expect(w.list_item(name)).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_watchlist_detail_add_remove_ticker(page, frontend_base_url, market) -> None:
    from apps.profiles.models import Watchlist

    wl = Watchlist.objects.get(name="E2E Core")
    d = WatchlistDetailPage(page, frontend_base_url)
    d.go(wl.id)
    d.expect_error_boundary_absent()
    d.add("NVDA")
    expect(d.ticker_row("NVDA")).to_be_visible(timeout=10_000)
    d.remove("NVDA")
    expect(d.ticker_row("NVDA")).to_have_count(0, timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_market_ticker_page_renders_ohlc_and_news(page, frontend_base_url, market) -> None:
    m = MarketTickerPage(page, frontend_base_url)
    m.go("AAPL")
    m.expect_error_boundary_absent()
    expect(m.ohlc_chart).to_be_visible(timeout=10_000)
    expect(m.chain_heading).to_be_visible()
    expect(m.news_heading).to_be_visible()
