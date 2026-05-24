"""Schwab OAuth status page — /settings#schwab."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class SchwabOAuthPage(BasePage):
    PATH = "/settings#schwab"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def connect_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Connect Schwab")

    @property
    def status_pill(self) -> Locator:
        return self.page.get_by_test_id("schwab-status")

    def connect(self) -> None:
        self.connect_btn.click()
