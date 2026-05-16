"""Journey 3 — create schedule, trigger run-now, notification arrives."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_FRONTEND_URL


@pytest.mark.integration
def test_observer_to_thread(page) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/schedules")
    page.get_by_role("button", name="Create schedule").click()
    page.get_by_label("Interval (seconds)").fill("60")
    page.get_by_role("button", name="Save").click()

    page.get_by_role("button", name="Run now").first.click()

    expect(page.get_by_test_id("notification-bell")).to_contain_text("1", timeout=30000)
