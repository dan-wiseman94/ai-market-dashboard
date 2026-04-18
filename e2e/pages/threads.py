from e2e.pages.base import BasePage


class ThreadsPage(BasePage):
    def go(self) -> None:
        self.goto("/threads")

    def new_thread_button(self):
        return self.page.get_by_role("button", name="New Thread")
