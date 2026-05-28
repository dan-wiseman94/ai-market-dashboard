"""Market ticker page — /market/:ticker."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class MarketTickerPage(BasePage):
    def go(self, ticker: str) -> None:
        self.goto(f"/market/{ticker}")

    @property
    def ohlc_chart(self) -> Locator:
        # Chart.tsx renders <div id="chart-root"> (also the headless-capture target).
        return self.page.locator("#chart-root")

    @property
    def chain_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="Option chain")

    @property
    def news_heading(self) -> Locator:
        return self.page.get_by_role("heading", name="News")

    @property
    def news_list(self) -> Locator:
        return self.page.get_by_role("list", name="news")

    @property
    def positions_tile(self) -> Locator:
        return self.page.get_by_test_id("positions-tile")
