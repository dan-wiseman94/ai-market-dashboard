"""Journey 4 — create always-fires trigger, fire it, check drill-down."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_FRONTEND_URL


@pytest.mark.integration
def test_trigger_firing(page) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/triggers/new")
    page.get_by_label("Name").fill("always")
    page.get_by_label("Ticker").fill("AAPL")
    page.get_by_label("Metric").select_option(value="last")
    page.get_by_label("Op").select_option(value=">")
    page.get_by_label("Value").fill("0")
    page.get_by_role("button", name="Save").click()

    page.get_by_role("button", name="Fire now").click()

    expect(page.get_by_test_id("notification-bell")).to_contain_text("1", timeout=30000)

    page.get_by_role("link", name="always").click()
    page.get_by_role("tab", name="Firings").click()
    expect(page.locator("text=fired")).to_have_count(1)
