"""Profiles gold + documented UI gaps."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.profiles import ProfilesPage


@pytest.mark.integration
@pytest.mark.ui
def test_profile_create_persists(page, frontend_base_url, minimal) -> None:
    """Creating a profile via the form persists it and renders its row."""
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    p.create(name="E2E Created Profile")
    expect(p.row("E2E Created Profile")).to_be_visible(timeout=10_000)
    from apps.profiles.models import TradingProfile

    assert TradingProfile.objects.filter(name="E2E Created Profile").exists()


@pytest.mark.integration
@pytest.mark.ui
def test_profile_flags_editable_in_ui(page, frontend_base_url, minimal) -> None:
    """The per-profile capability flags drive real AI behavior, so they are settable."""
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    expect(page.get_by_label("Enable tools")).to_be_visible(timeout=5_000)
    expect(page.get_by_label("Extended thinking")).to_be_visible()
    expect(page.get_by_label("Memory")).to_be_visible()
    expect(page.get_by_label("Decision Coach")).to_be_visible()
    # The budget appears only once extended thinking is on.
    expect(page.get_by_label("Thinking budget")).to_have_count(0)
    page.get_by_label("Extended thinking").click()
    expect(page.get_by_label("Thinking budget")).to_be_visible(timeout=5_000)


@pytest.mark.integration
@pytest.mark.ui
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    """A profile's active flag is settable from its row (the seed profile is active)."""
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    row = p.row("E2E Default")
    expect(row).to_be_visible(timeout=10_000)
    row.get_by_role("button", name="Deactivate").click(timeout=5_000)
    expect(p.row("E2E Default").get_by_role("button", name="Activate")).to_be_visible(
        timeout=10_000
    )
