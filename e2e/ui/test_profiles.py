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
    """The per-profile capability flags are settable from /profiles.

    These five gate tool use, extended thinking, memory and the Decision Coach on
    every run the profile drives. Exact matching matters here: "Tools" is a
    substring of nothing else on the form today, but "Active" is a substring of
    "Inactive" and the labels sit in one fieldset.
    """
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    for label in ("Tools", "Extended thinking", "Memory", "Decision Coach", "Effort"):
        expect(page.get_by_label(label, exact=True)).to_be_visible(timeout=5_000)


@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.xfail(
    reason="GAP: /profiles has no Activate affordance — there is no way to mark a profile active "
    "from the list UI. strict: when an activate control lands, the unexpected pass fails the "
    "run, forcing this marker's removal.",
    strict=True,
)
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    expect(p.row("E2E Default")).to_be_visible(timeout=10_000)
    # Attempt the (currently nonexistent) activate action — fails until the UI gains it.
    p.row("E2E Default").get_by_role("button", name="Activate").click(timeout=5_000)
