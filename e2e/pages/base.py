"""Base page object — shared navigation + common assertions.

Locators are properties (return ``page.get_by_...``).
Actions are methods.
Assertions live in tests — POMs never call ``expect(...)`` themselves.
"""

from __future__ import annotations

import platform

from playwright.sync_api import Locator, Page, expect

from e2e.helpers.waits import wait_for_app_ready


class BasePage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")

    def goto(self, path: str) -> None:
        self.page.goto(f"{self.base_url}{path}")
        self.wait_ready()

    def wait_ready(self) -> None:
        wait_for_app_ready(self.page)

    # --- shared locator properties ---
    @property
    def notification_bell(self) -> Locator:
        return self.page.get_by_test_id("notification-bell")

    @property
    def connection_dot(self) -> Locator:
        return self.page.get_by_test_id("connection-status-dot")

    @property
    def breadcrumb_trail(self) -> Locator:
        return self.page.get_by_test_id("breadcrumb-trail")

    # --- shared actions ---
    def expect_toast(self, text: str, kind: str = "info", timeout: int = 5_000) -> None:
        expect(self.page.get_by_test_id(f"toast-{kind}")).to_contain_text(text, timeout=timeout)

    def expect_error_boundary_absent(self) -> None:
        expect(self.page.get_by_text("Something went wrong", exact=False)).to_have_count(0)

    def open_command_palette(self) -> None:
        modifier = "Meta" if platform.system() == "Darwin" else "Control"
        self.page.keyboard.press(f"{modifier}+K")
        expect(self.page.get_by_test_id("command-palette")).to_be_visible()

    def run_shortcut(self, keys: str) -> None:
        """Press a chord like ``"g a"`` — splits on whitespace."""
        for key in keys.split():
            self.page.keyboard.press(key)

    def current_crumb_trail(self) -> list[str]:
        items = self.breadcrumb_trail.locator("li")
        return [items.nth(i).inner_text() for i in range(items.count())]
