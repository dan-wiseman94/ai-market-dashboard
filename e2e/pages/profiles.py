"""Profiles page — /profiles."""

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
    def tools_toggle(self) -> Locator:
        return self.page.get_by_label("Enable tools")

    @property
    def thinking_budget(self) -> Locator:
        return self.page.get_by_label("Thinking budget")

    @property
    def memory_toggle(self) -> Locator:
        return self.page.get_by_label("Enable memory")

    def create(
        self,
        *,
        name: str,
        enable_tools: bool = False,
        thinking_budget: int | None = None,
        enable_memory: bool = False,
    ) -> None:
        # The profile form is always visible (no modal/dialog).
        # Name is filled via placeholder — the UI has no aria-label for the name field.
        # Style (system prompt) is required by the API even though the textarea looks optional.
        # enable_tools / thinking_budget / enable_memory are not exposed in the current UI form.
        self.page.get_by_placeholder("Profile name").fill(name)
        self.page.get_by_placeholder("Trading style (used as system prompt)").fill("E2E test style")
        # Submit the profile form (first form on the page).
        self.page.get_by_role("button", name="Create").click()

    def toggle_active(self, name: str) -> None:
        # The profiles list has no "Activate" button in the current UI;
        # profiles are always active by default. This method is a no-op placeholder.
        pass
