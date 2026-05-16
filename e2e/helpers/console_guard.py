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
