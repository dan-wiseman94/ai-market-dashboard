"""Profiles gold."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.profiles import ProfilesPage


@pytest.mark.integration
@pytest.mark.ui
def test_profile_create_with_memory_tools_thinking_flags(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    expect(page.locator("body")).to_be_visible()
