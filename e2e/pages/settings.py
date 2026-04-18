from e2e.pages.base import BasePage


class SettingsPage(BasePage):
    def go(self) -> None:
        self.goto("/settings")

    def nav_link(self, label: str):
        return self.page.get_by_role("link", name=label)
