from e2e.pages.base import BasePage


class SchedulesPage(BasePage):
    def go(self) -> None:
        self.goto("/schedules")

    def schedule_row(self, name: str):
        return self.page.get_by_text(name).first
