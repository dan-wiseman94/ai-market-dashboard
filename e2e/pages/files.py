"""Files page — /files."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class FilesPage(BasePage):
    PATH = "/files"

    def go(self) -> None:
        self.goto(self.PATH)

    def row(self, file_id: str) -> Locator:
        return self.page.get_by_test_id(f"file-row-{file_id}")

    def upload(self, path: Path) -> None:
        self.page.set_input_files("input[type=file]", str(path))
        self.page.get_by_role("button", name="Upload").click()

    def delete(self, file_id: str) -> None:
        self.row(file_id).get_by_role("button", name="Delete").click()
