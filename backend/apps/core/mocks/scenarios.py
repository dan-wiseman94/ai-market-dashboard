"""Scenario registry — maps ``(scenario, service) → handler_name``.

Tests pick a scenario via the ``X-E2E-Scenario`` request header (parsed by
``ScenarioHeaderMiddleware``) or by calling ``apps.core.mocks.set_scenario()``
directly in unit-level code. Providers consult ``current_scenario()`` and dispatch
through ``providers.AI_HANDLERS`` / ``SERVICE_HANDLERS``.

Registry shape: ``{scenario_name: {service_name: handler_name}}``.
"""

from __future__ import annotations

SCENARIOS: dict[str, dict[str, str]] = {
    "default": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "claude-5xx": {
        "claude": "error_503_prestream",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "claude-5xx-midstream": {
        "claude": "stream_then_500",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "claude-ratelimit": {
        "claude": "error_429_retry_after",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "openai-timeout": {
        "claude": "stream_mocked_response",
        "openai": "hang_60s",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "schwab-401": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "error_401_token_expired",
        "finnhub": "ok",
        "files": "ok",
    },
    "schwab-oauth-ok": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "oauth_full_flow",
        "finnhub": "ok",
        "files": "ok",
    },
    "news-503": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "error_503",
        "files": "ok",
    },
    "cap-exceeded": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "files-upload-fail": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "error_500_on_upload",
    },
    "tool-use-loop": {
        "claude": "stream_tool_use_loop",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "thinking-heavy": {
        "claude": "stream_thinking_heavy",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "slow-stream": {
        "claude": "stream_slow",
        "openai": "stream_slow",
        "local": "stream_slow",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "structured-observation": {
        "claude": "structured_observation_report",
        "openai": "stream_mocked_response",
        "local": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
}


def handler_for(scenario: str, service: str) -> str:
    """Return the handler name for ``(scenario, service)``.

    Falls back to the default scenario's handler when the scenario or service
    is unknown.
    """
    default_table = SCENARIOS["default"]
    table = SCENARIOS.get(scenario, default_table)
    return table.get(service, default_table.get(service, "stream_mocked_response"))
