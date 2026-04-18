from e2e.pages.base import BasePage


class ExportPage(BasePage):
    def go(self) -> None:
        self.goto("/settings/export")

    def export_button(self):
        return self.page.get_by_role("button", name="Export")
