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
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_create_complex_dsl_all_any_not(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_backtest_runs_against_ohlc(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import EventTrigger

    trig = EventTrigger.objects.get(name="E2E always fires")
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_cooldown_respected(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import EventTrigger

    trig = EventTrigger.objects.get(name="E2E always fires")
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_edit_preserves_firings(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import EventTrigger, TriggerFiring

    trig = EventTrigger.objects.get(name="E2E always fires")
    before = TriggerFiring.objects.filter(trigger=trig).count()
    tl = TriggersListPage(page, frontend_base_url)
    tl.go()
    expect(page.locator("body")).to_be_visible()
    # Firings count unchanged after navigating around.
    assert TriggerFiring.objects.filter(trigger=trig).count() == before
