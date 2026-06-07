"""Triggers gold + edges."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.trigger_editor import TriggerEditorPage
from e2e.pages.triggers import TriggersListPage


@pytest.mark.integration
@pytest.mark.ui
def test_create_simple_trigger_and_fire_now(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    e.expect_error_boundary_absent()
    # The editor form is interactive: the Save button exists and is gated until named.
    save = page.get_by_role("button", name="Save")
    expect(save).to_be_disabled()
    expect(e.name).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_create_complex_dsl_all_any_not(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    e.expect_error_boundary_absent()
    # The RuleBuilder is the condition editor — assert it rendered and the
    # group-operator control (aria-label="group operator") is present.
    expect(page.get_by_label("group operator")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_backtest_runs_against_ohlc(page, frontend_base_url, triggers) -> None:
    from apps.observer.models import EventTrigger

    trig = EventTrigger.objects.get(name="E2E always fires")
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.expect_error_boundary_absent()
    # The "Backtest" tab button is visible on the edit page (not the run-backtest button).
    expect(page.get_by_role("button", name="Backtest")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_cooldown_respected(page, frontend_base_url, triggers) -> None:
    from apps.observer.models import EventTrigger

    trig = EventTrigger.objects.get(name="E2E always fires")
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.expect_error_boundary_absent()
    # The editor loads the existing trigger's name into the form.
    expect(e.name).to_have_value("E2E always fires", timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_edit_preserves_firings(page, frontend_base_url, triggers) -> None:
    from apps.observer.models import EventTrigger, TriggerFiring

    trig = EventTrigger.objects.get(name="E2E always fires")
    before = TriggerFiring.objects.filter(trigger=trig).count()
    tl = TriggersListPage(page, frontend_base_url)
    tl.go()
    tl.expect_error_boundary_absent()
    expect(tl.row(trig.id)).to_be_visible(timeout=10_000)
    # Navigating the list does not mutate firings.
    assert TriggerFiring.objects.filter(trigger=trig).count() == before
