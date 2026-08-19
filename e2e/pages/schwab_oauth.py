"""Schwab OAuth status page — /settings/connections."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class SchwabOAuthPage(BasePage):
    PATH = "/settings/connections"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def connect_btn(self) -> Locator:
        # Renders as "Connect Schwab" when not connected, "Reconnect" when connected.
        return self.page.get_by_role("button", name="Connect Schwab")

    @property
    def schwab_card(self) -> Locator:
        return self.page.get_by_test_id("schwab-card")

    @property
    def status_pill(self) -> Locator:
        # The pill span inside schwab_card (class ledger-pill, no data-testid).
        return self.schwab_card.locator(".ledger-pill")

    def connect(self) -> None:
        self.connect_btn.click()
