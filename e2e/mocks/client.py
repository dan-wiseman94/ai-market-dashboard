"""ScenarioClient — inject ``X-E2E-Scenario`` into both Playwright page + httpx api.

Usage:

    def test_something(scenario):
        scenario.use("claude-5xx-midstream")
        # ... subsequent page actions + api calls now carry the header ...
"""

from __future__ import annotations

from typing import Any


class ScenarioClient:
    """Thin wrapper that mirrors the scenario header to a browser page and an httpx client."""

    def __init__(self, page: Any, api: Any) -> None:
        self.page = page
        self.api = api
        self._current: str = "default"

    @property
    def current(self) -> str:
        return self._current

    def use(self, name: str) -> None:
        self._current = name
        if self.page is not None:
            self.page.set_extra_http_headers({"X-E2E-Scenario": name})
        if self.api is not None:
            self.api.headers["X-E2E-Scenario"] = name

    def reset(self) -> None:
        self.use("default")
