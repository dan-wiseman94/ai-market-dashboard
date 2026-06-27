"""Attach to a Playwright page so any console.error or unexpected 5xx fails the test.

Usage (UI lane conftest):

    @pytest.fixture(autouse=True)
    def _ui_console_guard(page, request):
        if not request.node.get_closest_marker("ui"):
            yield
            return
        errors = console_guard.attach(page)
        yield
        if errors:
            pytest.fail("Unexpected console/network errors:\\n" + "\\n".join(errors))
"""

from __future__ import annotations

import re
from typing import Any

ALLOWED_CONSOLE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"/render/chart"),  # known benign chart-render route warning
    re.compile(r"React DevTools"),
    # WebSocket / connection warnings — the Channels layer in the e2e overlay
    # doesn't always come up before the page mounts; the frontend's reconnect
    # logic handles it without surfacing to the user.
    re.compile(r"WebSocket connection to .*/ws/"),
    re.compile(r"WebSocket is closed before the connection is established"),
    re.compile(r"Failed to load resource.*websocket", re.IGNORECASE),
    re.compile(r"Failed to load resource:.*ERR_CONNECTION_REFUSED"),
    # Same-origin proxy 404s during page mount appear as a console.error from the
    # fetch wrapper. Scope the allowance to the specific endpoints that legitimately
    # 404 before their first row exists (the UI degrades to EmptyState) — an
    # UNEXPECTED 404 (e.g. a broken route hitting a missing endpoint) must still
    # fail the test, so do NOT allow a blanket "404 Not Found".
    re.compile(r"404 \(Not Found\).*/api/files/"),
    re.compile(r"404 \(Not Found\).*/api/(recall|predictions)/"),
    # NOTE: the React Router default-ErrorBoundary console error is intentionally
    # NOT allow-listed — it is the signature of navigating to a broken/unregistered
    # route, and must fail the test (was previously masked).
    # Cross-origin font preflights fail when ``scenario.use(...)`` sets the
    # X-E2E-Scenario header on every request — Google Fonts' CORS policy
    # doesn't whitelist it. The page falls back to system fonts cleanly.
    re.compile(r"Access to font at .* has been blocked by CORS policy"),
    re.compile(r"fonts\.gstatic\.com"),
    re.compile(r"Failed to load resource: net::ERR_FAILED"),
]


ALLOWED_NETWORK_PATHS: list[re.Pattern[str]] = [
    re.compile(r"/ws/"),  # websocket upgrades sometimes look like errors in devtools
]


def attach(page: Any) -> list[str]:
    """Subscribe to page events and return the live list that accumulates errors."""
    errors: list[str] = []

    def _on_console(msg: Any) -> None:
        if msg.type != "error":
            return
        text = msg.text
        if any(p.search(text) for p in ALLOWED_CONSOLE_PATTERNS):
            return
        errors.append(f"CONSOLE: {text}")

    def _on_pageerror(err: Any) -> None:
        errors.append(f"PAGEERROR: {err}")

    def _on_response(resp: Any) -> None:
        if resp.status >= 500 and not any(p.search(resp.url) for p in ALLOWED_NETWORK_PATHS):
            errors.append(f"NETWORK {resp.status}: {resp.url}")

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)
    page.on("response", _on_response)
    return errors
