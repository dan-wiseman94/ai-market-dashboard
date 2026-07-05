"""Export page — /settings/export."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class ExportPage(BasePage):
    PATH = "/settings/export"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def start_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Start export")

    def row(self, export_id: int) -> Locator:
        return self.page.get_by_test_id(f"export-row-{export_id}")

    def download_btn(self, export_id: int) -> Locator:
        return self.row(export_id).get_by_role("link", name="Download")

    def start(self) -> None:
        self.start_btn.click()

    def download(self, export_id: int) -> bytes:
        with self.page.expect_download() as info:
            self.download_btn(export_id).click()
        return Path(info.value.path()).read_bytes()
