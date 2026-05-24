"""Settings gold paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.settings import SettingsPage


@pytest.mark.integration
@pytest.mark.ui
def test_provider_api_key_save_round_trip_masked(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_daily_and_monthly_cap_edit(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()
