"""Thesis (second-brain) journeys — list, detail, run-postmortem, close form.

E2E coverage for theses / post-mortems / decision journal.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.theses import ThesesPage, ThesisDetailPage


@pytest.mark.integration
@pytest.mark.ui
def test_theses_list_renders_open_and_closed(page, frontend_base_url, thesis) -> None:
    from apps.thesis.models import Thesis

    open_t = Thesis.objects.get(title="E2E open thesis")
    closed_t = Thesis.objects.get(title="E2E closed thesis")

    p = ThesesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    expect(p.heading).to_be_visible()
    # Both seeded theses appear, split across the Open / Closed sections.
    expect(p.row(open_t.id)).to_be_visible()
    expect(p.row(closed_t.id)).to_be_visible()
    expect(p.row(open_t.id)).to_contain_text("AAPL")
    expect(p.row(closed_t.id)).to_contain_text("TSLA")


@pytest.mark.integration
@pytest.mark.ui
def test_thesis_detail_shows_postmortem_cards(page, frontend_base_url, thesis) -> None:
    from apps.thesis.models import Thesis
    from django.conf import settings

    open_t = Thesis.objects.get(title="E2E open thesis")

    d = ThesisDetailPage(page, frontend_base_url)
    d.go(open_t.id)
    d.expect_error_boundary_absent()
    expect(page.get_by_role("heading", name="E2E open thesis")).to_be_visible()
    # schedule_postmortems lays down one card per configured horizon (7/30/90).
    for horizon in settings.THESIS_POSTMORTEM_HORIZONS:
        expect(d.pm_card(horizon)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_thesis_run_postmortem_queues(page, frontend_base_url, thesis) -> None:
    from apps.thesis.models import Thesis

    open_t = Thesis.objects.get(title="E2E open thesis")

    d = ThesisDetailPage(page, frontend_base_url)
    d.go(open_t.id)
    expect(d.run_postmortem_btn).to_be_visible()
    d.run_postmortem_btn.click()
    # The mutation POSTs /run-postmortem/ and the page surfaces a success toast.
    d.expect_toast("Post-mortem queued", kind="success")


@pytest.mark.integration
@pytest.mark.ui
def test_thesis_close_form_opens(page, frontend_base_url, thesis) -> None:
    from apps.thesis.models import Thesis

    open_t = Thesis.objects.get(title="E2E open thesis")

    d = ThesisDetailPage(page, frontend_base_url)
    d.go(open_t.id)
    # The close control is only present while the thesis is open.
    expect(d.open_close_form_btn).to_be_visible()
    d.open_close_form_btn.click()
    expect(d.close_form).to_be_visible()
    expect(d.close_form.get_by_label("Outcome")).to_be_visible()
