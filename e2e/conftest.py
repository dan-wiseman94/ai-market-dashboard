"""E2E harness — Playwright browser + a healthy compose stack.

Run: make e2e  (or `make e2e-one t=<test_module>`).
Requires MOCK_EXTERNAL=true + apps/core/mocks.py for deterministic fixtures.
"""

from __future__ import annotations

import os
import time
import warnings
from collections.abc import Iterator

E2E_BASE_URL = os.environ.get("E2E_BASE_URL", "http://web:8000")
E2E_FRONTEND_URL = os.environ.get("E2E_FRONTEND_URL", "http://frontend:5173")


def pytest_configure(config):
    """Register custom markers so pytest doesn't warn about unknown marks."""
    config.addinivalue_line("markers", "e2e: end-to-end browser tests (require compose stack)")
    config.addinivalue_line("markers", "ui: UI lane browser tests")
    config.addinivalue_line("markers", "api: API lane httpx contract tests")
    config.addinivalue_line("markers", "ws: WebSocket lane tests")
    config.addinivalue_line("markers", "visual: visual regression tests")
    config.addinivalue_line("markers", "a11y: accessibility scan tests")
    config.addinivalue_line("markers", "perf: performance budget tests")


try:
    import pytest
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

    @pytest.fixture(scope="session")
    def playwright_session() -> Iterator[Playwright]:
        with sync_playwright() as p:
            yield p

    @pytest.fixture(scope="session")
    def browser(playwright_session: Playwright) -> Iterator[Browser]:
        b = playwright_session.chromium.launch(headless=True)
        yield b
        b.close()

    @pytest.fixture
    def context(browser: Browser) -> Iterator[BrowserContext]:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        yield ctx
        ctx.close()

    @pytest.fixture
    def page(context: BrowserContext) -> Page:
        return context.new_page()

except ImportError:
    pass  # playwright fixtures only needed for browser journeys


import pytest  # noqa: E402 — re-import unconditionally for non-playwright fixtures


@pytest.fixture(autouse=True, scope="session")
def _wait_for_stack() -> None:
    """Block session start until the Django API responds. Skippable for unit-level E2E tests."""
    if os.environ.get("E2E_SKIP_STACK_WAIT", "").lower() in ("1", "true"):
        return
    import httpx

    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            r = httpx.get(f"{E2E_BASE_URL}/api/health/", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    # Soft-fail: warn but don't exit; tests that need the stack will fail naturally.
    warnings.warn("E2E stack not healthy after 60s; browser journeys may fail", stacklevel=1)


@pytest.fixture
def seed_minimal_fixture() -> None:
    """Idempotent minimal seed for tests that need DB objects. Use as an explicit param."""
    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return E2E_BASE_URL


@pytest.fixture(scope="session")
def frontend_base_url() -> str:
    return E2E_FRONTEND_URL
