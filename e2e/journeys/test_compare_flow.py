"""Journey 2 — Compare across providers shows per-branch costs + totals."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_FRONTEND_URL


@pytest.mark.integration
def test_compare_flow(page) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/snapshot")
    page.get_by_label("Profile").select_option(label="E2E Default")
    page.get_by_label("Objective").fill("compare test")
    page.get_by_role("button", name="Capture").click()
    expect(page.get_by_text("complete", exact=False)).to_be_visible(timeout=30000)
    page.get_by_role("button", name="Send to AI").click()
    expect(page.get_by_text("Mocked response")).to_be_visible(timeout=15000)

    page.get_by_role("button", name="Compare").click()
    page.get_by_role("button", name="Send to 2 branches").click()

    expect(page.locator("[data-testid^='branch-cost-']")).to_have_count(2, timeout=15000)
    expect(page.get_by_text("2 branches")).to_be_visible()
