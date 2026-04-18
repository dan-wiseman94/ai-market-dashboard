from e2e.pages.base import BasePage


class CostsPage(BasePage):
    def go(self) -> None:
        self.goto("/costs")

    def total_for_provider(self, provider: str):
        return self.page.locator(f"text=/{provider}/i").first
