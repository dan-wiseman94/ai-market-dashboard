"""Deterministic readiness waits — the reliable replacement for ``networkidle``.

The SPA holds a long-lived WebSocket and polls ``/api/health`` on a timer, so the
network never goes idle. ``page.wait_for_load_state("networkidle")`` therefore
either burns its whole timeout or resolves in a race window — Playwright itself
discourages it. Wait for a positive signal instead: the app shell (``<main>``
from AppLayout) is mounted, and any data skeleton has detached.
"""

from __future__ import annotations

import contextlib
from typing import Any


def wait_for_app_ready(page: Any, *, timeout_ms: int = 10_000) -> None:
    """Block until the AppLayout shell is mounted and loading skeletons are gone.

    The AppLayout shell ``<main data-testid="app-shell">`` is rendered once the
    layout mounts — a deterministic "shell is up" signal. (A bare ``role=main``
    lookup is ambiguous: some pages render their own inner ``<main>``, so the
    testid anchors the layout shell specifically.) Then wait for any ``skeleton-*``
    placeholder to detach, which resolves immediately when none is present (a route
    with no skeletons) and otherwise waits for data to resolve. The skeleton wait is
    best-effort so a route that legitimately keeps a skeleton-like element doesn't
    hang the suite.
    """
    page.get_by_test_id("app-shell").wait_for(state="visible", timeout=timeout_ms)
    with contextlib.suppress(Exception):
        page.wait_for_selector("[data-testid^='skeleton-']", state="detached", timeout=5_000)
