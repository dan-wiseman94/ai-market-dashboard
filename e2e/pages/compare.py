"""Compare dialog driver — launched from the thread detail page (⇌ Compare)."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class CompareDialog(BasePage):
    @property
    def open_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Compare")

    @property
    def question(self) -> Locator:
        return self.page.get_by_placeholder("Your question to every branch")

    @property
    def add_branch_btn(self) -> Locator:
        return self.page.get_by_role("button", name="add branch")

    @property
    def dispatch_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Dispatch")

    @property
    def branch_costs(self) -> Locator:
        # Resolved AND pending costs both start with 'branch-cost-'.
        return self.page.locator("[data-testid^='branch-cost-']")

    @property
    def pending_costs(self) -> Locator:
        return self.page.locator("[data-testid^='branch-cost-pending-']")

    def open(self) -> None:
        self.open_btn.click()

    def add_branch(self) -> None:
        self.add_branch_btn.click()

    def dispatch(self, question: str) -> None:
        self.question.fill(question)
        self.dispatch_btn.click()
