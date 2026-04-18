from e2e.pages.base import BasePage


class SnapshotPage(BasePage):
    def go(self) -> None:
        self.goto("/snapshot")

    def capture_button(self):
        return self.page.get_by_role("button", name="Capture")
