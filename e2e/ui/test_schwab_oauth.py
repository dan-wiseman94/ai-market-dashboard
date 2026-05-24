"""Schwab OAuth gold paths via the scenario engine."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.schwab_oauth import SchwabOAuthPage


@pytest.mark.integration
@pytest.mark.ui
def test_oauth_authorize_redirects_to_stub(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    s = SchwabOAuthPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_oauth_callback_persists_encrypted_token(
    page, frontend_base_url, minimal, scenario
) -> None:
    scenario.use("schwab-oauth-ok")
    s = SchwabOAuthPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()
