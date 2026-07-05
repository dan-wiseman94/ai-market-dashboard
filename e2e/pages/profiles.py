"""Profiles page — /profiles.

The /profiles create form exposes only name, trading style, and default
provider. The per-profile capability flags (enable_tools / enable_memory /
thinking_budget) exist on the model but are NOT editable here — see the xfail
test in test_profiles.py.
"""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class ProfilesPage(BasePage):
    PATH = "/profiles"

    def go(self) -> None:
        self.goto(self.PATH)

    def row(self, name: str) -> Locator:
        return self.page.get_by_test_id(f"profile-row-{name}")

    @property
    def name_input(self) -> Locator:
        return self.page.get_by_placeholder("Profile name")

    @property
    def style_input(self) -> Locator:
        return self.page.get_by_placeholder("Trading style (used as system prompt)")

    @property
    def create_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Create")

    def create(self, name: str, style: str = "E2E test style") -> None:
        # Style is required by the API even though the textarea looks optional.
        self.name_input.fill(name)
        self.style_input.fill(style)
        self.create_btn.click()
