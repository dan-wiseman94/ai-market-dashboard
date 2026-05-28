"""Market events page — /events."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class EventsPage(BasePage):
    PATH = "/events"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def heading(self) -> Locator:
        return self.page.get_by_role("heading", level=1)

    @property
    def earnings_section(self) -> Locator:
        return self.page.get_by_role("heading", name="Upcoming earnings")

    @property
    def macro_section(self) -> Locator:
        return self.page.get_by_role("heading", name="Macro calendar")
