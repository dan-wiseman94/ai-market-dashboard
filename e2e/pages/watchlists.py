"""Watchlists list page — /watchlists."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class WatchlistsPage(BasePage):
    PATH = "/watchlists"

    def go(self) -> None:
        self.goto(self.PATH)

    def list_item(self, name: str) -> Locator:
        return self.page.get_by_test_id(f"watchlist-row-{name}")

    @property
    def create_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Create")

    def create(self, name: str) -> None:
        self.page.get_by_placeholder("New watchlist name").fill(name)
        self.create_btn.click()

    def open(self, name: str) -> None:
        self.list_item(name).click()
