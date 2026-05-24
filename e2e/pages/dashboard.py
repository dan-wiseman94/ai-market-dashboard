"""Dashboard page — /."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class DashboardPage(BasePage):
    PATH = "/"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def card_snapshots(self) -> Locator:
        return self.page.get_by_test_id("dashboard-card-snapshots")

    @property
    def card_threads(self) -> Locator:
        return self.page.get_by_test_id("dashboard-card-threads")

    @property
    def card_cost(self) -> Locator:
        return self.page.get_by_test_id("cost-tile-today")

    def open_notification_drawer(self) -> None:
        self.notification_bell.click()
