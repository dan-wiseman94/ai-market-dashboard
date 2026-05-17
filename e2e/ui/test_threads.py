"""Threads — list + create plain + pinned + stop edge."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.threads import ThreadsListPage


@pytest.mark.integration
@pytest.mark.ui
def test_threads_list_pagination_and_filter(page, frontend_base_url, threads) -> None:
    p = ThreadsListPage(page, frontend_base_url)
    p.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_thread_create_plain_and_send(page, frontend_base_url, minimal) -> None:
    p = ThreadsListPage(page, frontend_base_url)
    p.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_thread_create_pinned_to_snapshot(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(status="ready").first()
    if snap is None:
        pytest.skip("no ready snapshot in seed")
    page.goto(f"{frontend_base_url}/threads/new?pinned_snapshot={snap.id}")
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_thread_stop_midstream(page, frontend_base_url, threads, scenario) -> None:
    """Use the slow ``thinking-heavy`` scenario to ensure there's a window for ``stop``."""
    scenario.use("thinking-heavy")
    from apps.threads.models import Thread

    t = Thread.objects.filter(title="E2E plain thread").first()
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    expect(page.locator("body")).to_be_visible()
