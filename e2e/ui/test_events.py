"""Market events page gold path."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.events import EventsPage


@pytest.mark.integration
@pytest.mark.ui
def test_events_page_renders(page, frontend_base_url, market) -> None:
    e = EventsPage(page, frontend_base_url)
    e.go()
    e.expect_error_boundary_absent()
    # The page renders its two sections (earnings + macro), each with data or an empty state.
    expect(e.earnings_section).to_be_visible(timeout=10_000)
    expect(e.macro_section).to_be_visible()
