from e2e.pages.base import BasePage


class DashboardPage(BasePage):
    def go(self) -> None:
        self.goto("/")

    def notification_bell(self):
        return self.page.get_by_test_id("notification-bell")
