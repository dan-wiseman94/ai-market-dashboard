"""Watchlist detail page — /watchlists/:id."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class WatchlistDetailPage(BasePage):
    def go(self, watchlist_id: int) -> None:
        self.goto(f"/watchlists/{watchlist_id}")

    def ticker_row(self, ticker: str) -> Locator:
        return self.page.get_by_role("row", name=ticker)

    @property
    def add_input(self) -> Locator:
        return self.page.get_by_placeholder("Add ticker (e.g. SPY)")

    def remove_btn(self, ticker: str) -> Locator:
        return self.ticker_row(ticker).get_by_role("button", name="Remove")

    def add(self, ticker: str) -> None:
        self.add_input.fill(ticker)
        self.page.get_by_role("button", name="Add").click()

    def remove(self, ticker: str) -> None:
        self.remove_btn(ticker).click()
