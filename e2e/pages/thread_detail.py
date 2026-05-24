"""Thread detail page — /threads/:id."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, expect

from e2e.pages.base import BasePage


class ThreadDetailPage(BasePage):
    def go(self, thread_id: int) -> None:
        self.goto(f"/threads/{thread_id}")

    def message(self, message_id: int) -> Locator:
        return self.page.get_by_test_id(f"message-{message_id}")

    @property
    def compose(self) -> Locator:
        return self.page.get_by_test_id("compose-input")

    @property
    def stop_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Stop")

    def branch_tab(self, n: int) -> Locator:
        return self.page.get_by_role("tab", name=f"Branch {n}")

    def cost_tile(self, n: int) -> Locator:
        return self.page.get_by_test_id(f"branch-cost-{n}")

    def send(self, text: str) -> None:
        self.compose.fill(text)
        self.page.get_by_role("button", name="Send").click()

    def stop(self) -> None:
        self.stop_btn.click()

    def attach_file(self, path: Path) -> None:
        self.page.get_by_role("button", name="Attach").click()
        self.page.set_input_files("input[type=file]", str(path))

    def wait_for_done(self, timeout: int = 15_000) -> None:
        expect(self.page.get_by_text("Mocked response")).to_be_visible(timeout=timeout)
