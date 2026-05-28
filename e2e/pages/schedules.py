"""Observer schedules page — /schedules."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class SchedulesPage(BasePage):
    PATH = "/schedules"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def create_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Create schedule")

    @property
    def interval_input(self) -> Locator:
        return self.page.get_by_label("Interval (seconds)")

    @property
    def mode_select(self) -> Locator:
        return self.page.get_by_label("Mode")

    @property
    def structured_toggle(self) -> Locator:
        return self.page.get_by_label("Structured")

    def schedule_row(self, schedule_id: int) -> Locator:
        return self.page.get_by_test_id(f"schedule-row-{schedule_id}")

    def run_now_btn(self, schedule_id: int) -> Locator:
        return self.schedule_row(schedule_id).get_by_role("button", name="Run now")

    def enabled_checkbox(self, schedule_id: int) -> Locator:
        # Each row carries a single "enabled" checkbox (pause = uncheck it).
        return self.schedule_row(schedule_id).get_by_role("checkbox")

    def create(self, interval: int, mode: str = "full", structured: bool = False) -> None:
        self.create_btn.click()
        self.interval_input.fill(str(interval))
        if mode != "full":
            self.mode_select.select_option(value=mode)
        if structured:
            self.structured_toggle.check()
        self.page.get_by_role("button", name="Save").click()

    def run_now(self, schedule_id: int) -> None:
        self.run_now_btn(schedule_id).click()

    def set_enabled(self, schedule_id: int, enabled: bool) -> None:
        # The checkbox is controlled by server state via an async mutation, so a click
        # fires the toggle but the box only re-renders after the refetch — callers must
        # wait for the eventual state (expect(...).to_be_checked()). We click only when
        # the current state differs from the target.
        cb = self.enabled_checkbox(schedule_id)
        if cb.is_checked() != enabled:
            cb.click()
