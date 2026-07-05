"""Backups page — /settings/backups."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class BackupsPage(BasePage):
    PATH = "/settings/backups"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def backup_now_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Back up now")

    def row(self, backup_id: int) -> Locator:
        return self.page.get_by_test_id(f"backup-row-{backup_id}")

    def restore_btn(self, backup_id: int) -> Locator:
        return self.row(backup_id).get_by_role("button", name="Restore")

    def download_btn(self, backup_id: int) -> Locator:
        return self.row(backup_id).get_by_role("link", name="Download")

    def backup_now(self) -> None:
        self.backup_now_btn.click()

    def restore(self, backup_id: int) -> None:
        self.restore_btn(backup_id).click()

    def download(self, backup_id: int) -> bytes:
        with self.page.expect_download() as info:
            self.download_btn(backup_id).click()
        return Path(info.value.path()).read_bytes()
