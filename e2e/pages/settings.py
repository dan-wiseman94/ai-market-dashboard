"""Settings page — /settings."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class SettingsPage(BasePage):
    PATH = "/settings"

    def go(self) -> None:
        self.goto(self.PATH)

    def api_key_input(self, provider: str) -> Locator:
        return self.page.get_by_label(f"{provider} API key")

    @property
    def save_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Save")

    def nav_link(self, label: str) -> Locator:
        return self.page.get_by_role("link", name=label)

    def save_api_key(self, provider: str, key: str) -> None:
        self.api_key_input(provider).fill(key)
        self.save_btn.click()
