"""E2E harness — Playwright browser + a healthy compose stack.

Run: make e2e  (or `make e2e-one t=<lane>/<file>.py`).
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
        b = playwright_session.chromium.launch(headless=os.environ.get("HEADED") != "1")
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


@pytest.fixture(autouse=True)
def _unblock_live_db_for_e2e(request, django_db_blocker):
    """Bypass pytest-django's safety net for tests under e2e/ that write to the live DB.

    The api/, ui/, ws/, visual/, a11y/, perf/ lanes seed data via Django ORM but the
    running web container reads from the same live Postgres — they must share a
    database. pytest-django would normally redirect ORM calls to a per-process test
    DB or block them outright; we explicitly unblock here so seeds land where the
    server reads them.

    Also unblocks ``e2e/tests/test_seed_ladder.py``: those tests exercise the same
    idempotent seed functions and would otherwise fight the api lane (the rolled-back
    transactions wipe shared rows the api tests rely on).

    Tests that explicitly use ``@pytest.mark.django_db`` keep that behavior — the
    blocker is already unblocked for them by pytest-django itself.
    """
    test_path = str(request.node.fspath)
    is_e2e_lane = any(
        f"/e2e/{lane}/" in test_path for lane in ("api", "ui", "ws", "visual", "a11y", "perf")
    )
    is_seed_ladder = test_path.endswith("e2e/tests/test_seed_ladder.py")
    if not (is_e2e_lane or is_seed_ladder):
        yield
        return
    with django_db_blocker.unblock():
        yield


@pytest.fixture(scope="session")
def api_base_url() -> str:
    return E2E_BASE_URL


@pytest.fixture(scope="session")
def ws_base_url() -> str:
    explicit = os.environ.get("E2E_WS_URL")
    if explicit:
        return explicit
    # Container-internal Channels traffic — no public exposure, no TLS termination.
    scheme = "ws"  # nosem: insecure-websocket — internal-only test stack, not production
    return f"{scheme}://web:8000"


@pytest.fixture(scope="session")
def frontend_base_url() -> str:
    return E2E_FRONTEND_URL


# ---------------------------------------------------------------------------
# Seed ladder — 7 rungs, each depends on the previous. Tests declare only the
# highest rung they need; everything below runs automatically.
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal() -> None:
    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()


@pytest.fixture
def market(minimal) -> None:
    from e2e.fixtures.seed_market import seed_market

    seed_market()


@pytest.fixture
def snapshots(market) -> None:
    from e2e.fixtures.seed_snapshots import seed_snapshots

    seed_snapshots()


@pytest.fixture
def threads(snapshots) -> None:
    from e2e.fixtures.seed_threads import seed_threads

    seed_threads()


@pytest.fixture
def observer(threads) -> None:
    from e2e.fixtures.seed_observer import seed_observer

    seed_observer()


@pytest.fixture
def triggers(observer) -> None:
    from e2e.fixtures.seed_triggers import seed_triggers

    seed_triggers()


@pytest.fixture
def analytics(triggers) -> None:
    from e2e.fixtures.seed_analytics import seed_analytics

    seed_analytics()


@pytest.fixture
def thesis(threads) -> None:
    from e2e.fixtures.seed_thesis import seed_thesis

    seed_thesis()


# ---------------------------------------------------------------------------
# Scenario engine client — injects X-E2E-Scenario into the Playwright page and
# the httpx api_client.
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(api_base_url):
    import httpx

    with httpx.Client(base_url=api_base_url, timeout=15) as client:
        yield client


@pytest.fixture
def scenario(page, api_client):
    from e2e.mocks.client import ScenarioClient

    c = ScenarioClient(page, api_client)
    yield c
    c.reset()
