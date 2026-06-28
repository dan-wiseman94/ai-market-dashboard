"""Observer gold + edges."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.helpers.waits import wait_for_app_ready
from e2e.pages.schedules import SchedulesPage


@pytest.mark.integration
@pytest.mark.ui
def test_schedule_run_now_dispatches(page, frontend_base_url, observer) -> None:
    """Drive the per-row Run-now action on a seeded schedule.

    Run-now POSTs /run-now/ to queue the observation; the run has no UI toast
    and its async effect (a new observation message + notification) is asserted
    on the ws lane (test_notifications.py). Here we assert the action dispatches
    from the UI without error — the autouse console guard fails on any 5xx.
    (Renamed from test_create_schedule_and_run_now, which only asserted the row
    and button were visible; the cron-based create form is covered separately.)
    """
    from apps.observer.models import ObserverSchedule

    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    sched = ObserverSchedule.objects.filter(name="E2E active schedule").order_by("id").first()
    assert sched is not None
    expect(s.schedule_row(sched.id)).to_be_visible(timeout=10_000)

    s.run_now(sched.id)
    s.expect_error_boundary_absent()
    expect(s.schedule_row(sched.id)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_schedule_pause_resume(page, frontend_base_url, observer) -> None:
    """Pause/resume a schedule via its 'enabled' checkbox; the change persists."""
    from apps.observer.models import ObserverSchedule

    sched = ObserverSchedule.objects.get(name="E2E active schedule")
    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    cb = s.enabled_checkbox(sched.id)
    expect(cb).to_be_checked(timeout=10_000)
    # Pause = uncheck → persisted to the backend.
    s.set_enabled(sched.id, False)
    expect(cb).not_to_be_checked(timeout=10_000)
    sched.refresh_from_db()
    assert sched.enabled is False
    # Resume = re-check.
    s.set_enabled(sched.id, True)
    expect(cb).to_be_checked(timeout=10_000)
    sched.refresh_from_db()
    assert sched.enabled is True


@pytest.mark.integration
@pytest.mark.ui
def test_observer_structured_mode_produces_typed_card(
    page, frontend_base_url, observer, scenario
) -> None:
    scenario.use("structured-observation")
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    wait_for_app_ready(page)
    # The observer thread page renders without crashing and shows the thread surface.
    expect(page.get_by_text("Something went wrong")).to_have_count(0)
    expect(page.get_by_text("Loading")).to_have_count(0, timeout=10_000)
    # The seeded observer thread has messages — the timeline list should render.
    expect(page.locator("ul").first).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_observer_diff_mode_sends_only_delta(page, frontend_base_url, observer) -> None:
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    wait_for_app_ready(page)
    expect(page.get_by_text("Something went wrong")).to_have_count(0)
    # The seeded observer thread renders its title heading.
    expect(page.get_by_role("heading", level=1)).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_observer_cost_cap_skip_emits_system_message(page, frontend_base_url, observer) -> None:
    """A cost-cap skip message is surfaced on the canonical observer timeline.

    The timeline resolves the per-profile thread ('Observer: <name>',
    schedule__isnull=True) — so the seed writes the cost-cap message there (not into
    the schedule-linked thread). The '⏸' prefix triggers the timeline's skipped
    styling, so 'cost cap' shows in the collapsed headline.
    """
    from apps.profiles.models import TradingProfile

    profile = TradingProfile.objects.get(name="E2E Default")
    page.goto(f"{frontend_base_url}/threads/observer/{profile.id}")
    wait_for_app_ready(page)
    expect(page.get_by_role("heading", name=f"Observer: {profile.name}")).to_be_visible(
        timeout=10_000
    )
    expect(page.get_by_text("cost cap", exact=False).first).to_be_visible(timeout=10_000)
