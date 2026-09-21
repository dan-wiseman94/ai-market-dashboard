"""Profiles page — /profiles.

The create form exposes name, trading style, default sections, the default AI
target (provider + model) and the per-profile capability controls (Enable tools /
Extended thinking + its budget / Effort / Memory + its store / Decision Coach /
Active). Each row carries Edit, Activate-or-Deactivate and Delete.

Match capability labels with ``exact=True``: "Memory" is a prefix of the memory
store's own label, and "Active" is a substring of the "Inactive" row pill.
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
