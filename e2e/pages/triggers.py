"""Triggers list page — /triggers."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class TriggersListPage(BasePage):
    PATH = "/triggers"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def new_btn(self) -> Locator:
        return self.page.get_by_role("link", name="New trigger")

    def row(self, trigger_id: int) -> Locator:
        return self.page.get_by_test_id(f"trigger-row-{trigger_id}")

    def firings_tab(self) -> Locator:
        return self.page.get_by_role("tab", name="Firings")

    def open(self, trigger_id: int) -> None:
        self.row(trigger_id).click()


# Back-compat alias.
TriggersPage = TriggersListPage
