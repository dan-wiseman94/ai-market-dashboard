"""Page-level visual snapshots for every top-level route.

Baselines: ``e2e/visual/__screenshots__/<test>/linux/<name>.png``. Regenerate
with ``make e2e-visual-update``.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from e2e.helpers.visual import default_masks, wait_for_stable

ROUTES: list[tuple[str, str, str]] = [
    ("/", "analytics", "dashboard"),
    ("/settings", "minimal", "settings_general"),
    ("/settings/backups", "minimal", "settings_backups"),
    ("/settings/export", "threads", "settings_export"),
    ("/watchlists", "market", "watchlists_list"),
    ("/market/AAPL", "market", "market_ticker"),
    ("/profiles", "minimal", "profiles"),
    ("/snapshot", "minimal", "snapshot_composer_empty"),
    ("/threads", "threads", "threads_list"),
    ("/costs", "analytics", "costs_today"),
    ("/schedules", "observer", "schedules"),
    ("/triggers", "triggers", "triggers_list"),
    ("/triggers/new", "minimal", "trigger_editor"),
    ("/analytics", "analytics", "analytics"),
]


@pytest.mark.integration
@pytest.mark.visual
@pytest.mark.parametrize("path,rung,name", ROUTES)
def test_route_snapshot(
    page: Page, frontend_base_url: str, path: str, rung: str, name: str, request
) -> None:
    request.getfixturevalue(rung)
    page.goto(f"{frontend_base_url}{path}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name=f"{name}.png", mask=default_masks(page), max_diff_pixel_ratio=0.02
    )


@pytest.mark.integration
@pytest.mark.visual
def test_watchlist_detail_snapshot(page: Page, frontend_base_url: str, market) -> None:
    from apps.profiles.models import Watchlist

    wl = Watchlist.objects.get(name="E2E Core")
    page.goto(f"{frontend_base_url}/watchlists/{wl.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name="watchlist_detail.png", mask=default_masks(page), max_diff_pixel_ratio=0.02
    )


@pytest.mark.integration
@pytest.mark.visual
def test_thread_detail_plain_snapshot(page: Page, frontend_base_url: str, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name="thread_detail_plain.png",
        mask=default_masks(page),
        max_diff_pixel_ratio=0.02,
    )


@pytest.mark.integration
@pytest.mark.visual
def test_thread_detail_compare_snapshot(page: Page, frontend_base_url: str, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E compare thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name="thread_detail_compare.png",
        mask=default_masks(page),
        max_diff_pixel_ratio=0.02,
    )


@pytest.mark.integration
@pytest.mark.visual
def test_snapshot_cost_drill_snapshot(page: Page, frontend_base_url: str, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    s = Snapshot.objects.filter(status="ready").first()
    page.goto(f"{frontend_base_url}/costs/snapshot/{s.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name="snapshot_cost_drill.png",
        mask=default_masks(page),
        max_diff_pixel_ratio=0.02,
    )


@pytest.mark.integration
@pytest.mark.visual
def test_observer_timeline_snapshot(page: Page, frontend_base_url: str, observer) -> None:
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name="observer_timeline.png",
        mask=default_masks(page),
        max_diff_pixel_ratio=0.02,
    )
