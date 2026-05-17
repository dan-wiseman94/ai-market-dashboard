"""API lane conftest — fast feedback loop, no browser.

The session-scoped ``api_base_url`` fixture is defined in the top-level
``e2e/conftest.py``. We add an httpx ``api_client`` here scoped to the api lane
so it stays lightweight and doesn't compete with Playwright.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest


@pytest.fixture
def api_client(api_base_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=api_base_url, timeout=15) as client:
        yield client
