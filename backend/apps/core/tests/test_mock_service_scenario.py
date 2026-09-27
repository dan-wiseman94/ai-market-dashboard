"""run_service_scenario() — the gate that turns a (scenario, service) mapping into
behavior: raise for error scenarios, return the canned handler result otherwise."""

from apps.core.mocks import reset_scenario, run_service_scenario, set_scenario


def test_oauth_scenario_returns_payload():
    set_scenario("schwab-oauth-ok")
    try:
        result = run_service_scenario("schwab")
    finally:
        reset_scenario()
    assert "authorize_url" in result
    assert "tokens" in result
