"""Snapshot cost drill-down page — /costs/snapshot/:id."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class SnapshotCostPage(BasePage):
    def go(self, snapshot_id: int) -> None:
        self.goto(f"/costs/snapshot/{snapshot_id}")

    def section_row(self, name: str) -> Locator:
        return self.page.get_by_role("row", name=name)

    @property
    def cost_total(self) -> Locator:
        return self.page.get_by_test_id("cost-total")
