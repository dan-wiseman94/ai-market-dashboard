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
        self.page.get_by_role("button", name="New profile").click()
        self.page.get_by_label("Name").fill(name)
        if enable_tools:
            self.tools_toggle.check()
        if thinking_budget is not None:
            self.thinking_budget.fill(str(thinking_budget))
        if enable_memory:
            self.memory_toggle.check()
        self.page.get_by_role("button", name="Save").click()

    def toggle_active(self, name: str) -> None:
        self.row(name).get_by_role("button", name="Activate").click()
