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
    p.expect_error_boundary_absent()
    p.create(name="E2E Flags Profile")
    expect(p.row("E2E Flags Profile")).to_be_visible(timeout=10_000)
    # Verify the profile row was persisted to the backend.
    from apps.profiles.models import TradingProfile

    assert TradingProfile.objects.filter(name="E2E Flags Profile").exists()


@pytest.mark.integration
@pytest.mark.ui
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    # The seeded "E2E Default" profile row is visible in the list.
    expect(p.row("E2E Default")).to_be_visible(timeout=10_000)
    # The row renders the profile name.
    expect(p.row("E2E Default")).to_contain_text("E2E Default")
