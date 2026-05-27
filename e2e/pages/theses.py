"""Thesis pages — /theses (list) and /theses/<id> (detail)."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class ThesesPage(BasePage):
    PATH = "/theses"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def heading(self) -> Locator:
        return self.page.get_by_role("heading", name="Theses")

    @property
    def empty_state(self) -> Locator:
        return self.page.get_by_text("No theses yet")

    def row(self, thesis_id: int) -> Locator:
        return self.page.get_by_test_id(f"thesis-row-{thesis_id}")

    def open(self, thesis_id: int) -> None:
        self.row(thesis_id).get_by_role("link", name="View thesis", exact=False).click()


class ThesisDetailPage(BasePage):
    def go(self, thesis_id: int) -> None:
        self.goto(f"/theses/{thesis_id}")

    @property
    def run_postmortem_btn(self) -> Locator:
        return self.page.get_by_test_id("run-postmortem-btn")

    @property
    def open_close_form_btn(self) -> Locator:
        return self.page.get_by_test_id("open-close-form-btn")

    @property
    def close_form(self) -> Locator:
        return self.page.get_by_test_id("close-thesis-form")

    def pm_card(self, horizon_days: int) -> Locator:
        return self.page.get_by_test_id(f"pm-card-{horizon_days}")
