"""Snapshot composer page — /snapshot."""

from __future__ import annotations

from playwright.sync_api import Locator, expect

from e2e.pages.base import BasePage


class SnapshotPage(BasePage):
    PATH = "/snapshot"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def profile_select(self) -> Locator:
        return self.page.get_by_label("Profile")

    @property
    def objective_input(self) -> Locator:
        return self.page.get_by_label("Objective")

    @property
    def capture_btn(self) -> Locator:
        return self.page.get_by_test_id("capture-btn")

    @property
    def send_ai_btn(self) -> Locator:
        return self.page.get_by_test_id("send-ai-btn")

    def section_status(self, kind: str) -> Locator:
        return self.page.get_by_test_id(f"section-{kind}-status")

    def capture(self, profile: str, objective: str, sections: list[str] | None = None) -> None:
        self.profile_select.select_option(label=profile)
        self.objective_input.fill(objective)
        if sections is not None:
            for label in sections:
                self.page.get_by_label(label).check()
        self.capture_btn.click()

    def wait_for_complete(self, timeout: int = 30_000) -> None:
        expect(self.page.get_by_text("complete", exact=False)).to_be_visible(timeout=timeout)

    def send_to_ai(self) -> None:
        self.send_ai_btn.click()

    def open_compare(self) -> None:
        self.page.get_by_role("button", name="Compare").click()
