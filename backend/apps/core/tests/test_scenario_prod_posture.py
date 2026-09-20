"""The E2E scenario engine must be invisible unless MOCK_EXTERNAL is on.

Two independent gates carry that promise:

* ``apps/core/urls.py`` registers ``_scenario_probe/`` / ``_mock_ping_claude/``
  only when the env var is truthy, read at import time.
* ``config/settings/base.py`` appends ``ScenarioHeaderMiddleware`` under the
  same condition, so the ``X-E2E-Scenario`` header is inert without it.

Both branches run here rather than against a live stack: the overlay is the only
stack the e2e lanes bring up and it always sets ``MOCK_EXTERNAL=true``, so a
lane-based prod-posture test can never reach its assertion.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from django.conf import settings

import apps.core

URLS_PATH = Path(apps.core.__file__).parent / "urls.py"
SCENARIO_ROUTES = {"scenario-probe", "mock-ping-claude"}


def _route_names_with_env(monkeypatch, value: str | None) -> set[str]:
    """Exec a fresh copy of apps/core/urls.py under a chosen MOCK_EXTERNAL.

    Loaded under a throwaway module name so ``sys.modules["apps.core.urls"]``
    and Django's resolver cache are left untouched.
    """
    if value is None:
        monkeypatch.delenv("MOCK_EXTERNAL", raising=False)
    else:
        monkeypatch.setenv("MOCK_EXTERNAL", value)

    spec = importlib.util.spec_from_file_location("apps.core._urls_posture_probe", URLS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "apps.core"  # keeps `from . import views` resolving
    spec.loader.exec_module(module)
    return {p.name for p in module.urlpatterns}


@pytest.mark.parametrize("value", [None, "", "false", "0", "no"])
def test_scenario_routes_absent_without_mock_external(monkeypatch, value) -> None:
    names = _route_names_with_env(monkeypatch, value)
    assert not (names & SCENARIO_ROUTES)
    assert "health" in names  # the module really did load


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_scenario_routes_present_under_mock_external(monkeypatch, value) -> None:
    assert _route_names_with_env(monkeypatch, value) >= SCENARIO_ROUTES


def test_scenario_middleware_tracks_mock_external() -> None:
    """Installed exactly when MOCK_EXTERNAL is on — never unconditionally."""
    installed = "apps.core.mocks.middleware.ScenarioHeaderMiddleware" in settings.MIDDLEWARE
    assert installed is bool(settings.MOCK_EXTERNAL)


@pytest.mark.django_db
def test_scenario_header_is_inert_without_the_middleware(client) -> None:
    """A stray X-E2E-Scenario header must not change a real response.

    Asserts the unit-lane precondition instead of skipping on it: MOCK_EXTERNAL
    on a dev/test stack is itself the bug CLAUDE.md warns about (provider patch
    sites sit below the short-circuit and silently serve canned fixtures).
    """
    assert not settings.MOCK_EXTERNAL, "unit lane must not run under MOCK_EXTERNAL"

    plain = client.get("/api/health/")
    tainted = client.get("/api/health/", headers={"X-E2E-Scenario": "claude-5xx"})
    assert tainted.status_code == plain.status_code == 200
    assert tainted.json() == plain.json()
