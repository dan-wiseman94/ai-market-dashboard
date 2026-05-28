"""Page-level visual snapshots for every top-level route.

Baselines: ``e2e/visual/__screenshots__/<name>.png``. On first run the test
creates the baseline. Subsequent runs compare bytes; failures write
``<name>.actual.png`` next to the baseline.

Regenerate baselines: ``make e2e-visual-update`` (deletes the directory and
re-runs the lane).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from e2e.helpers.visual import capture_or_compare, default_masks, wait_for_stable

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
    # /costs is intentionally omitted from the byte-diff lane: the seeded
    # AIRun amounts are random and bleed into multiple dollar-formatted
    # cells that aren't reachable by a single mask selector. Tracked
    # under the "byte-diff sharpness" limitation in e2e/README.md;
    # revisit when we switch to a pixel-tolerance diff library.
    ("/schedules", "observer", "schedules"),
    ("/triggers", "triggers", "triggers_list"),
    ("/triggers/new", "minimal", "trigger_editor"),
    ("/analytics", "analytics", "analytics"),
    # Thesis list rows carry no timestamps, so the byte-diff stays stable.
    ("/theses", "thesis", "theses_list"),
    # Briefing on the minimal rung shows the static empty state (no BriefingRun).
    ("/briefing", "minimal", "briefing_empty"),
    # Events with no seeded MarketEvent rows shows the static empty sections.
    ("/events", "minimal", "events_empty"),
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
    capture_or_compare(page, name, mask=default_masks(page))


@pytest.mark.integration
@pytest.mark.visual
def test_watchlist_detail_snapshot(page: Page, frontend_base_url: str, market) -> None:
    from apps.profiles.models import Watchlist

    wl = Watchlist.objects.get(name="E2E Core")
    page.goto(f"{frontend_base_url}/watchlists/{wl.id}")
    wait_for_stable(page)
    capture_or_compare(page, "watchlist_detail", mask=default_masks(page))


@pytest.mark.integration
@pytest.mark.visual
def test_thread_detail_plain_snapshot(page: Page, frontend_base_url: str, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    wait_for_stable(page)
    capture_or_compare(page, "thread_detail_plain", mask=default_masks(page))


@pytest.mark.integration
@pytest.mark.visual
def test_thread_detail_compare_snapshot(page: Page, frontend_base_url: str, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E compare thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    wait_for_stable(page)
    capture_or_compare(page, "thread_detail_compare", mask=default_masks(page))


@pytest.mark.integration
@pytest.mark.visual
def test_snapshot_cost_drill_snapshot(page: Page, frontend_base_url: str, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    s = Snapshot.objects.filter(status="ready").first()
    page.goto(f"{frontend_base_url}/costs/snapshot/{s.id}")
    wait_for_stable(page)
    capture_or_compare(page, "snapshot_cost_drill", mask=default_masks(page))


@pytest.mark.integration
@pytest.mark.visual
def test_observer_timeline_snapshot(page: Page, frontend_base_url: str, observer) -> None:
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    wait_for_stable(page)
    capture_or_compare(page, "observer_timeline", mask=default_masks(page))
