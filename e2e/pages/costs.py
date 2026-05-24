"""Costs page — /costs."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class CostsPage(BasePage):
    PATH = "/costs"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def today_tile(self) -> Locator:
        return self.page.get_by_test_id("cost-tile-today")

    @property
    def provider_table(self) -> Locator:
        return self.page.get_by_role("table", name="Provider costs")

    @property
    def csv_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Export CSV")

    @property
    def caps_editor(self) -> Locator:
        return self.page.get_by_test_id("caps-editor")

    def total_for_provider(self, provider: str) -> Locator:
        return self.page.locator(f"text=/{provider}/i").first

    def export_csv(self) -> bytes:
        with self.page.expect_download() as info:
            self.csv_btn.click()
        return Path(info.value.path()).read_bytes()

    def set_caps(self, *, daily: str, monthly: str) -> None:
        self.caps_editor.get_by_label("Daily cap (USD)").fill(daily)
        self.caps_editor.get_by_label("Monthly cap (USD)").fill(monthly)
        self.page.get_by_role("button", name="Save caps").click()
