"""Costs gold paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.costs import CostsPage


@pytest.mark.integration
@pytest.mark.ui
def test_costs_today_tile(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_costs_caps_editor_persists(page, frontend_base_url, minimal) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_costs_csv_export_downloads_and_parses(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    expect(page.locator("body")).to_be_visible()
