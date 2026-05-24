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

    def pause_btn(self, schedule_id: int) -> Locator:
        return self.schedule_row(schedule_id).get_by_role("button", name="Pause")

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

    def pause(self, schedule_id: int) -> None:
        self.pause_btn(schedule_id).click()
