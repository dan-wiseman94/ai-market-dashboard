"""Analytics page — /analytics."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class AnalyticsPage(BasePage):
    PATH = "/analytics"

    def go(self) -> None:
        self.goto(self.PATH)

    def card(self, kind: str) -> Locator:
        return self.page.get_by_test_id(f"analytics-card-{kind}")

    @property
    def card_leaderboard(self) -> Locator:
        return self.card("leaderboard")

    @property
    def card_cpi(self) -> Locator:
        return self.card("cpi")

    @property
    def card_heatmap(self) -> Locator:
        return self.card("heatmap")

    @property
    def card_timeline(self) -> Locator:
        return self.card("timeline")

    def card_unusual(self, _ticker: str | None = None) -> Locator:
        return self.card("unusual-options")

    def set_ticker(self, sym: str) -> None:
        self.page.get_by_label("Ticker").fill(sym)

    def set_forward_hours(self, n: int) -> None:
        self.page.get_by_label("Forward hours").fill(str(n))
