"""Keyboard shortcuts + command palette.

The ``g <x>`` chord map mirrors SHORTCUTS in
frontend/src/hooks/useKeyboardShortcuts.ts. Each chord is asserted to actually
navigate — a regression in any single shortcut fails its own parametrized case.
(Previously a single test looped over a subset and swallowed failures with
``except Exception: continue``, so it could never fail and covered only 7/13.)
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from e2e.pages.dashboard import DashboardPage

# g <key> → destination path. Full map (all 13 chords).
SHORTCUTS: dict[str, str] = {
    "d": "/",
    "s": "/snapshot",
    "t": "/triggers",
    "h": "/threads",
    "c": "/costs",
    "o": "/schedules",
    "a": "/analytics",
    "j": "/theses",
    "e": "/events",
    "b": "/briefing",
    "k": "/scorecard",
    "n": "/snapshots",
    "r": "/recall",
}


def _on_path(expected: str):
    """Predicate for ``wait_for_url`` that compares only the pathname (ignores
    trailing slash and origin)."""
    want = expected.rstrip("/") or "/"

    def _matcher(url: str) -> bool:
        path = urlparse(url).path.rstrip("/") or "/"
        return path == want

    return _matcher


@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.parametrize("key,expected", sorted(SHORTCUTS.items()))
def test_g_shortcut_navigates(page, frontend_base_url, minimal, key, expected) -> None:
    d = DashboardPage(page, frontend_base_url)
    # Start on a page that is NOT the destination so the navigation is observable
    # (otherwise `g d` from the dashboard would be a no-op tautology).
    d.goto("/costs" if expected == "/" else "/")
    page.keyboard.press("Escape")
    d.run_shortcut(f"g {key}")
    # wait_for_url raising on timeout IS the assertion — no try/except.
    page.wait_for_url(_on_path(expected), timeout=4_000)


@pytest.mark.integration
@pytest.mark.ui
def test_cmd_k_palette_opens(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # CommandPalette is mounted in AppLayout; Cmd/Ctrl-K opens it.
    # open_command_palette() asserts the palette becomes visible.
    d.open_command_palette()


@pytest.mark.integration
@pytest.mark.ui
def test_command_palette_executes_navigation(page, frontend_base_url, minimal) -> None:
    """Open the palette, filter to a command, run it, and assert it navigates.

    Previously only the open was asserted; this drives an actual command
    (the default commands are nav actions, e.g. "Go to Costs" -> /costs).
    """
    d = DashboardPage(page, frontend_base_url)
    d.go()
    d.open_command_palette()
    palette = page.get_by_test_id("command-palette")
    palette.get_by_placeholder("Search commands", exact=False).fill("Costs")
    palette.get_by_text("Go to Costs").click()
    page.wait_for_url(lambda u: u.rstrip("/").endswith("/costs"), timeout=5_000)
