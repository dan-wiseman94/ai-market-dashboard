"""Dashboard page — /."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class DashboardPage(BasePage):
    PATH = "/"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def hero_heading(self) -> Locator:
        return self.page.locator("h1").first

    @property
    def market_context_section(self) -> Locator:
        return self.page.get_by_role("heading", name="Market context")

    @property
    def book_section(self) -> Locator:
        return self.page.get_by_role("heading", name="The book")

    @property
    def cost_chip(self) -> Locator:
        """The CostChip link in the header — always rendered, shows today's spend."""
        return self.page.get_by_role("link", name="Today")

    # Legacy aliases kept for backwards compat with any existing references.
    @property
    def card_snapshots(self) -> Locator:
        return self.market_context_section

    @property
    def card_threads(self) -> Locator:
        return self.book_section

    @property
    def card_cost(self) -> Locator:
        return self.cost_chip

    def open_notification_drawer(self) -> None:
        self.notification_bell.click()
