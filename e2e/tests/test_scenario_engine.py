"""Scenario engine — ContextVar + registry + middleware probe."""

from __future__ import annotations

import os

import httpx
import pytest


def test_mocks_package_importable() -> None:
    from apps.core.mocks import current_scenario, set_scenario  # noqa: F401


def test_default_scenario_is_default() -> None:
    from apps.core.mocks import current_scenario, reset_scenario

    reset_scenario()
    assert current_scenario() == "default"


def test_set_scenario_round_trip() -> None:
    from apps.core.mocks import current_scenario, reset_scenario, set_scenario

    set_scenario("claude-5xx")
    try:
        assert current_scenario() == "claude-5xx"
    finally:
        reset_scenario()


def test_registry_has_fourteen_scenarios() -> None:
    from apps.core.mocks.scenarios import SCENARIOS

    expected = {
        "default",
        "claude-5xx",
        "claude-5xx-midstream",
        "claude-ratelimit",
        "openai-timeout",
        "schwab-401",
        "schwab-oauth-ok",
        "news-503",
        "cap-exceeded",
        "files-upload-fail",
        "tool-use-loop",
        "thinking-heavy",
        "slow-stream",
        "structured-observation",
    }
    assert set(SCENARIOS.keys()) == expected


def test_registry_default_entry_has_all_services() -> None:
    from apps.core.mocks.scenarios import SCENARIOS

    default = SCENARIOS["default"]
    for svc in ("claude", "openai", "schwab", "finnhub", "files"):
        assert svc in default


def test_handler_for_falls_back_to_default() -> None:
    from apps.core.mocks.scenarios import handler_for

    # Unknown scenario falls back to default mapping
    assert handler_for("nonexistent", "claude") == "stream_mocked_response"
    # Unknown service falls back to default's default
    assert handler_for("default", "nonexistent") == "stream_mocked_response"


@pytest.mark.integration
def test_middleware_sets_scenario_from_header(api_base_url) -> None:
    """When MOCK_EXTERNAL is on, the header drives current_scenario()."""
    r = httpx.get(
        f"{api_base_url}/api/_scenario_probe/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=5,
    )
    assert r.status_code == 200
    assert r.json()["scenario"] == "claude-5xx"


@pytest.mark.integration
def test_middleware_noop_without_header(api_base_url) -> None:
    r = httpx.get(f"{api_base_url}/api/_scenario_probe/", timeout=5)
    assert r.status_code == 200
    assert r.json()["scenario"] == "default"


@pytest.mark.integration
def test_claude_provider_honors_claude_5xx_scenario(api_base_url) -> None:
    """The mock dispatch raises for claude-5xx → /_mock_ping_claude/ returns 503."""
    r = httpx.post(
        f"{api_base_url}/api/_mock_ping_claude/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=10,
    )
    # POST not allowed (we registered as GET) — use GET
    r = httpx.get(
        f"{api_base_url}/api/_mock_ping_claude/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=10,
    )
    assert r.status_code == 503
    assert "RuntimeError" in r.json().get("error_kind", "")


@pytest.mark.integration
def test_claude_provider_default_scenario_returns_events(api_base_url) -> None:
    r = httpx.get(f"{api_base_url}/api/_mock_ping_claude/", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["events"] >= 1
    assert body["scenario"] == "default"


@pytest.mark.integration
def test_prod_guard_scenario_probe_404_without_mock_external() -> None:
    """When MOCK_EXTERNAL is off, the probe endpoint must not be registered.

    Skip when the e2e overlay is active — both the env var AND the resolved Django
    setting are consulted because ``os.environ`` can be empty in some test contexts
    even though ``settings.MOCK_EXTERNAL`` is True.
    """
    from django.conf import settings

    overlay_on = os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true", "yes") or getattr(
        settings, "MOCK_EXTERNAL", False
    )
    if overlay_on:
        pytest.skip("e2e overlay is up; this test is prod-posture-only")

    import httpx as _httpx

    r = _httpx.get("http://web:8000/api/_scenario_probe/", timeout=3)
    assert r.status_code == 404
