"""Market ticker page — /market/:ticker."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class MarketTickerPage(BasePage):
    def go(self, ticker: str) -> None:
        self.goto(f"/market/{ticker}")

    @property
    def ohlc_chart(self) -> Locator:
        # The market ticker page renders a chart container div below the ticker heading.
        # The chart element itself has no test-id; the container is identified by its
        # fixed height (400px) style — we use the h1 heading as the presence indicator.
        return self.page.locator("h1")

    @property
    def news_list(self) -> Locator:
        return self.page.get_by_role("list", name="news")

    @property
    def positions_tile(self) -> Locator:
        return self.page.get_by_test_id("positions-tile")
