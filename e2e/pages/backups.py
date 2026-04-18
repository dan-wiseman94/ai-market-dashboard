from e2e.pages.base import BasePage


class BackupsPage(BasePage):
    def go(self) -> None:
        self.goto("/settings/backups")

    def backup_now_button(self):
        return self.page.get_by_role("button", name="Backup Now")
