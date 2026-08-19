"""Observer schedule create flow — /schedules.

Drives the real create form (the SchedulesPage POM's create() was stale): the
"+ New schedule" toggle reveals the form (name + profile + fire-mode + cron),
and Create persists the schedule. Assert it persists and appears in the list.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.schedules import SchedulesPage


@pytest.mark.integration
@pytest.mark.ui
def test_create_schedule_via_form(page, frontend_base_url, minimal) -> None:
    from apps.observer.models import ObserverSchedule

    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()

    page.get_by_role("button", name="New schedule").click()
    page.get_by_label("Name").fill("E2E created schedule")
    page.get_by_label("Profile").select_option(index=0)  # first profile (no placeholder option)
    create = page.get_by_role("button", name="Create", exact=True)
    expect(create).to_be_enabled(timeout=10_000)
    create.click()

    expect(page.get_by_text("E2E created schedule")).to_be_visible(timeout=10_000)
    assert ObserverSchedule.objects.filter(name="E2E created schedule").exists()
