"""Observer timeline page — /threads/observer/:profileId."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class ObserverTimelinePage(BasePage):
    def go(self, profile_id: int) -> None:
        self.goto(f"/threads/observer/{profile_id}")

    @property
    def fire_rows(self) -> Locator:
        return self.page.locator("[data-testid^='fire-row-']")

    def fire_row(self, firing_id: int) -> Locator:
        return self.page.get_by_test_id(f"fire-row-{firing_id}")

    def scroll_to_day(self, date_iso: str) -> None:
        self.page.get_by_text(date_iso).scroll_into_view_if_needed()
