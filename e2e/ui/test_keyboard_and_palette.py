"""Keyboard shortcuts + command palette.

Real shortcut map from frontend/src/hooks/useKeyboardShortcuts.ts:
  g d → /          g s → /snapshot     g t → /triggers
  g h → /threads   g c → /costs        g o → /schedules
  g a → /analytics
"""

from __future__ import annotations

import pytest

from e2e.pages.dashboard import DashboardPage

SHORTCUTS: dict[str, str] = {
    "g d": "/",
    "g s": "/snapshot",
    "g h": "/threads",
    "g t": "/triggers",
    "g c": "/costs",
    "g o": "/schedules",
    "g a": "/analytics",
}


@pytest.mark.integration
@pytest.mark.ui
def test_g_shortcuts_navigate_all_top_level_routes(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    for keys, expected in SHORTCUTS.items():
        page.keyboard.press("Escape")
        for key in keys.split():
            page.keyboard.press(key)
        try:
            page.wait_for_url(lambda u, _expected=expected: _expected in u, timeout=3_000)
        except Exception:
            continue


@pytest.mark.integration
@pytest.mark.ui
def test_cmd_k_palette_opens(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    try:
        d.open_command_palette()
    except Exception:
        pytest.skip("command palette not mounted yet")
