"""Morning Briefing page — /briefing."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class BriefingPage(BasePage):
    PATH = "/briefing"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def run_now_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Run now")

    @property
    def heading(self) -> Locator:
        # The briefing content renders an <h1> once a run exists.
        return self.page.get_by_role("heading", level=1)

    def run_now(self) -> None:
        self.run_now_btn.click()
