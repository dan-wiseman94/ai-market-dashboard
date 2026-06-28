"""Snapshot capture + ask flow — /snapshot.

Drives the real capture (previously the composer was only asserted to render its
Capture button): select a profile, set an objective, click "Capture + ask". The
snapshot captures asynchronously in a Celery worker, then a pinned consult thread
is created and the page navigates to it. Assert a ready snapshot was created and
the navigation landed on a thread.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.snapshot import SnapshotPage


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_capture_and_ask(page, frontend_base_url, market) -> None:
    from apps.snapshots.models import Snapshot

    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()

    # The capture button is gated only on a selected profile.
    page.get_by_label("Profile").select_option(index=1)
    page.get_by_placeholder("What do you want the AI to consider", exact=False).fill(
        "E2E capture objective"
    )
    capture = page.get_by_test_id("capture-btn")
    expect(capture).to_be_enabled(timeout=10_000)
    capture.click()

    # Capture + ask: the snapshot captures async (Celery worker), then a pinned
    # consult thread is created and the page navigates to it. Generous timeout for
    # the worker round-trip.
    page.wait_for_url(lambda u: "/threads/" in u, timeout=60_000)

    snap = Snapshot.objects.filter(objective="E2E capture objective").order_by("-id").first()
    assert snap is not None, "a snapshot was created from the capture"
    assert snap.status == "ready", f"snapshot reached ready (was {snap.status})"
