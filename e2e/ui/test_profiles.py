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
@pytest.mark.xfail(
    reason="GAP: /profiles create form exposes no per-profile capability toggles. "
    "TradingProfile.enable_tools / enable_memory / thinking_budget exist on the model and "
    "drive real AI behavior, but ProfilesPage.tsx renders only name/style/provider — so they "
    "cannot be set from the UI. Flips to XPASS when the flag controls are added.",
    strict=False,
)
def test_profile_flags_editable_in_ui(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    expect(page.get_by_label("Enable tools")).to_be_visible(timeout=5_000)


@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.xfail(
    reason="GAP: /profiles has no Activate affordance — there is no way to mark a profile active "
    "from the list UI. Flips to XPASS when an activate control is added.",
    strict=False,
)
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    expect(p.row("E2E Default")).to_be_visible(timeout=10_000)
    # Attempt the (currently nonexistent) activate action — fails until the UI gains it.
    p.row("E2E Default").get_by_role("button", name="Activate").click(timeout=5_000)
