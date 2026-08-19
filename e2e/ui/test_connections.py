"""Schwab connections page — /settings/connections.

The page was never browser-tested (the SchwabOAuthPage POM was dead code; the
OAuth round-trip is API-tested in test_schwab_oauth.py). Assert the connection
card renders its real affordances: the status pill, the connect/reconnect
button, and the app-config credential fields.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from e2e.pages.schwab_oauth import SchwabOAuthPage


@pytest.mark.integration
@pytest.mark.ui
def test_connections_schwab_card_renders(page, frontend_base_url, minimal) -> None:
    p = SchwabOAuthPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()

    expect(p.schwab_card).to_be_visible(timeout=10_000)
    # The status pill resolves to a definite Connected / Not connected state.
    expect(p.status_pill).to_contain_text(re.compile(r"connected", re.IGNORECASE))
    connect = page.get_by_role("button", name="Connect Schwab").or_(
        page.get_by_role("button", name="Reconnect")
    )
    expect(connect).to_be_visible()
    expect(page.get_by_label("Schwab App Key")).to_be_visible()
