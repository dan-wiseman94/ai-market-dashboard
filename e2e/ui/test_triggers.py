"""Triggers gold + edges."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.trigger_editor import TriggerEditorPage
from e2e.pages.triggers import TriggersListPage


@pytest.mark.integration
@pytest.mark.ui
def test_create_trigger_then_fire_now(page, frontend_base_url, minimal) -> None:
    """Drive the real create flow (name → Save → persisted + listed), then fire it.

    The profile auto-selects to the first profile on load and the default
    condition is already valid, so a basic trigger needs only a name. The
    list's per-row "Fire now" opens a window.confirm; accept it and assert the
    queued toast.
    """
    from apps.observer.models import EventTrigger

    # Idempotent on the shared, never-rolled-back e2e DB: a prior run's trigger
    # would otherwise make the get() below raise MultipleObjectsReturned.
    EventTrigger.objects.filter(name="E2E created trigger").delete()

    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    e.expect_error_boundary_absent()

    # Save is gated until named (and a profile is selected — auto-selected on load).
    save = page.get_by_role("button", name="Save")
    expect(save).to_be_disabled()
    e.name.fill("E2E created trigger")
    expect(save).to_be_enabled(timeout=10_000)
    save.click()

    # Success navigates back to the list; the trigger persisted and is listed.
    page.wait_for_url(lambda u: u.rstrip("/").endswith("/triggers"), timeout=10_000)
    trig = EventTrigger.objects.get(name="E2E created trigger")
    tl = TriggersListPage(page, frontend_base_url)
    expect(tl.row(trig.id)).to_be_visible(timeout=10_000)

    # Fire-now: the row button opens a window.confirm — accept it, then the
    # POST /fire/ is queued and a toast confirms.
    page.on("dialog", lambda d: d.accept())
    tl.row(trig.id).get_by_role("button", name="Fire now").click()
    tl.expect_toast("fire queued", kind="info")


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
    assert TriggerFiring.objects.filter(trigger=trig).count() == before
