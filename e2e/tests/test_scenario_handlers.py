"""Meta-test: every scenario handler name is actually registered.

``handler_for`` / ``get_ai_stream_for_scenario`` / ``get_service_result`` SILENTLY
fall back to a default handler (``stream_mocked_response`` / ``ok``) when a scenario
references a handler name that is not in the registry — so a typo'd or removed
handler would make a scenario quietly exercise nothing special. Assert every
``(scenario, service)`` handler name resolves to a real registered handler.
"""

from __future__ import annotations

# AI services dispatch through AI_HANDLERS; everything else through SERVICE_HANDLERS.
AI_SERVICES = {"claude", "openai", "local"}


def test_every_scenario_handler_is_registered() -> None:
    from apps.core.mocks.providers import AI_HANDLERS, SERVICE_HANDLERS
    from apps.core.mocks.scenarios import SCENARIOS

    unregistered: list[str] = []
    for scenario, services in SCENARIOS.items():
        for service, handler_name in services.items():
            registry = AI_HANDLERS if service in AI_SERVICES else SERVICE_HANDLERS
            if handler_name not in registry:
                unregistered.append(f"{scenario}.{service} -> {handler_name!r}")

    assert not unregistered, (
        "scenario handler names not found in the registry (handler_for would "
        "silently fall back to the default): " + ", ".join(unregistered)
    )


def test_default_scenario_covers_every_service() -> None:
    """The 'default' scenario must map every service, since handler_for falls back
    to it for any scenario that omits a service."""
    from apps.core.mocks.scenarios import SCENARIOS

    expected = {"claude", "openai", "local", "schwab", "finnhub", "files"}
    assert set(SCENARIOS["default"]) == expected, (
        f"default scenario must map all services; missing {expected - set(SCENARIOS['default'])}"
    )
