"""Threads list page — /threads."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class ThreadsListPage(BasePage):
    PATH = "/threads"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def filter_input(self) -> Locator:
        return self.page.get_by_label("Filter")

    @property
    def pagination_next(self) -> Locator:
        return self.page.get_by_role("button", name="Next")

    def thread_row(self, thread_id: int) -> Locator:
        return self.page.get_by_test_id(f"thread-row-{thread_id}")

    def open(self, thread_id: int) -> None:
        self.thread_row(thread_id).click()

    def filter(self, text: str) -> None:
        self.filter_input.fill(text)


# Back-compat alias for existing Phase 0 tests that import ThreadsPage.
ThreadsPage = ThreadsListPage
