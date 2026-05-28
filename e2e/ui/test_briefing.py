"""Morning Briefing page gold path."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.briefing import BriefingPage


@pytest.mark.integration
@pytest.mark.ui
def test_briefing_page_renders(page, frontend_base_url, minimal) -> None:
    b = BriefingPage(page, frontend_base_url)
    b.go()
    b.expect_error_boundary_absent()
    # Whether or not a run exists yet, the page always offers a Run-now control.
    expect(b.run_now_btn).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_briefing_run_now_renders_content(page, frontend_base_url, minimal) -> None:
    b = BriefingPage(page, frontend_base_url)
    b.go()
    b.expect_error_boundary_absent()
    b.run_now()
    # run_briefing assembles deterministic data sections synchronously; the latest
    # run then renders its heading (AI synthesis is best-effort and may be absent).
    expect(b.heading).to_be_visible(timeout=30_000)
