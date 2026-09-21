"""Profiles gold: the capability controls and the row-level activate control."""

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
    """The per-profile capability controls are settable from /profiles.

    These gate tool use, extended thinking, reasoning effort, memory and the
    Decision Coach on every run the profile drives. Exact matching matters here:
    "Memory" is a prefix of the memory store's own label and "Active" is a
    substring of the "Inactive" row pill, and the controls sit in one fieldset.
    """
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    labels = ("Enable tools", "Extended thinking", "Effort", "Memory", "Decision Coach", "Active")
    for label in labels:
        expect(page.get_by_label(label, exact=True)).to_be_visible(timeout=5_000)
    # A new profile inherits the model defaults, which have thinking ON, so the
    # budget starts visible and goes away with the switch.
    expect(page.get_by_label("Thinking budget", exact=True)).to_be_visible()
    page.get_by_label("Extended thinking", exact=True).click()
    expect(page.get_by_label("Thinking budget", exact=True)).to_have_count(0)


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
