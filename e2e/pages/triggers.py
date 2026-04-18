from e2e.pages.base import BasePage


class TriggersPage(BasePage):
    def go(self) -> None:
        self.goto("/triggers")

    def trigger_row(self, name: str):
        return self.page.get_by_text(name).first
