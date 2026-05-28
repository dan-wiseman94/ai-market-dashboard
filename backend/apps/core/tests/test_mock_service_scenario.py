"""run_service_scenario() — the gate that turns a (scenario, service) mapping into
behavior: raise for error scenarios, return the canned handler result otherwise."""

import pytest

from apps.core.mocks import reset_scenario, run_service_scenario, set_scenario


def test_default_scenario_resolves_to_ok():
    reset_scenario()
    assert run_service_scenario("finnhub") == {"status": "ok"}


def test_error_scenario_raises():
    set_scenario("news-503")
    try:
        with pytest.raises(RuntimeError, match="503"):
            run_service_scenario("finnhub")
    finally:
        reset_scenario()


def test_oauth_scenario_returns_payload():
    set_scenario("schwab-oauth-ok")
    try:
        result = run_service_scenario("schwab")
    finally:
        reset_scenario()
    assert "authorize_url" in result
    assert "tokens" in result


def test_unknown_service_falls_back_to_ok():
    # default's fallback handler name is an AI handler not in SERVICE_HANDLERS;
    # get_service_result resolves the miss to ok().
    reset_scenario()
    assert run_service_scenario("nonexistent-service") == {"status": "ok"}
