"""Thesis create flow — /theses/new.

Drives the real create (the route previously had no ui coverage): fill the
pre-trade-discipline-required fields (rationale + an invalidation), submit, and
assert it persists and navigates to the new thesis. The server-side discipline
*rejection* (empty rationale / missing invalidation) is covered at the API
contract level (apps/thesis); the form's own ``required`` attributes make the
rejection path unreachable through the browser anyway.
"""

from __future__ import annotations

import pytest

from e2e.pages.base import BasePage


@pytest.mark.integration
@pytest.mark.ui
def test_create_thesis_persists_and_navigates(page, frontend_base_url, minimal) -> None:
    from apps.thesis.models import Thesis

    base = BasePage(page, frontend_base_url)
    base.goto("/theses/new")
    base.expect_error_boundary_absent()

    page.get_by_label("Title").fill("E2E NVDA thesis")
    page.get_by_label("Rationale", exact=False).fill("E2E rationale: momentum + an earnings beat.")
    page.get_by_label("Ticker").fill("NVDA")
    page.get_by_label("What would invalidate this thesis?").fill("A daily close below 100.")
    page.get_by_role("button", name="Create thesis").click()

    # Success navigates to the new thesis detail page (…/theses/<id>, not /new).
    page.wait_for_url(
        lambda u: "/theses/" in u and not u.rstrip("/").endswith("/new"), timeout=10_000
    )
    t = Thesis.objects.get(title="E2E NVDA thesis")
    assert t.rationale, "rationale persisted"
    assert t.invalidation_price or t.invalidation_note, "an invalidation persisted (discipline)"
