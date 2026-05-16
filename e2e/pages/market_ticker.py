"""Market ticker page — /market/:ticker."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class MarketTickerPage(BasePage):
    def go(self, ticker: str) -> None:
        self.goto(f"/market/{ticker}")

    @property
    def ohlc_chart(self) -> Locator:
        return self.page.locator("[data-chart='ohlc']")

    @property
    def news_list(self) -> Locator:
        return self.page.get_by_role("list", name="news")

    @property
    def positions_tile(self) -> Locator:
        return self.page.get_by_test_id("positions-tile")
