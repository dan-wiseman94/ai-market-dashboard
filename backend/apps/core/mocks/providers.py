"""Deterministic external-API mocks (activated when MOCK_EXTERNAL=true).

In addition to the legacy ``is_mock_mode()`` / ``canned_ai_stream()`` helpers, this
module exposes named *scenario handlers*. The scenario registry
(``apps.core.mocks.scenarios``) maps ``(scenario, service)`` pairs to a handler
function name in this module; providers consult ``current_scenario()`` then
look up the matching handler here.

Handlers are intentionally lightweight: they describe behavior, not transport.
Provider modules adapt them to their own event types.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


def is_mock_mode() -> bool:
    return os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true", "yes")


@dataclass
class MockAIEvent:
    type: str
    text: str = ""


def canned_ai_stream() -> list[MockAIEvent]:
    return [
        MockAIEvent("text_delta", "Mocked "),
        MockAIEvent("text_delta", "response"),
        MockAIEvent("usage"),
        MockAIEvent("done"),
    ]


# ---------------------------------------------------------------------------
# AI scenario streams — each returns a list of MockAIEvent
# ---------------------------------------------------------------------------


def stream_mocked_response() -> list[MockAIEvent]:
    return canned_ai_stream()


def error_503_prestream() -> list[MockAIEvent]:
    raise RuntimeError("provider_503: mock scenario claude-5xx")


def stream_then_500() -> list[MockAIEvent]:
    return [
        MockAIEvent("text_delta", "partial"),
        MockAIEvent("text_delta", " bytes"),
        MockAIEvent("error", "provider_500: mock scenario claude-5xx-midstream"),
    ]


def error_429_retry_after() -> list[MockAIEvent]:
    raise RuntimeError("provider_429_retry_after=30")


def hang_60s() -> list[MockAIEvent]:
    import time

    time.sleep(60)
    return []


def stream_tool_use_loop() -> list[MockAIEvent]:
    return [
        MockAIEvent("tool_call", "quotes_now"),
        MockAIEvent("tool_result", "175.0"),
        MockAIEvent("text_delta", "Result: 175"),
        MockAIEvent("usage"),
        MockAIEvent("done"),
    ]


def stream_thinking_heavy() -> list[MockAIEvent]:
    return [
        MockAIEvent("thinking_delta", "thinking..."),
        MockAIEvent("thinking_delta", "thinking..."),
        MockAIEvent("thinking_delta", "thinking..."),
        MockAIEvent("text_delta", "here is my answer"),
        MockAIEvent("usage"),
        MockAIEvent("done"),
    ]


def structured_observation_report() -> list[MockAIEvent]:
    return [
        MockAIEvent(
            "text_delta",
            '{"summary":"bullish","signals":[],"risks":[]}',
        ),
        MockAIEvent("usage"),
        MockAIEvent("done"),
    ]


# ---------------------------------------------------------------------------
# Non-AI service handlers
# ---------------------------------------------------------------------------


def ok(*_args, **_kwargs) -> dict:
    return {"status": "ok"}


def error_503(*_args, **_kwargs) -> None:
    raise RuntimeError("provider_503")


def error_401_token_expired(*_args, **_kwargs) -> None:
    raise RuntimeError("401_token_expired")


def oauth_full_flow(*_args, **_kwargs) -> dict:
    return {
        "authorize_url": "http://localhost:8000/schwab/callback?code=MOCK_OAUTH",
        "tokens": {"access": "mock", "refresh": "mock"},
    }


def error_500_on_upload(*_args, **_kwargs) -> None:
    raise RuntimeError("files_upload_500")


# ---------------------------------------------------------------------------
# Static dispatch tables — no dynamic lookup, no globals().
# Adding a new handler means appending it here.
# ---------------------------------------------------------------------------


AI_HANDLERS: dict[str, Callable[[], list[MockAIEvent]]] = {
    "stream_mocked_response": stream_mocked_response,
    "error_503_prestream": error_503_prestream,
    "stream_then_500": stream_then_500,
    "error_429_retry_after": error_429_retry_after,
    "hang_60s": hang_60s,
    "stream_tool_use_loop": stream_tool_use_loop,
    "stream_thinking_heavy": stream_thinking_heavy,
    "structured_observation_report": structured_observation_report,
}


SERVICE_HANDLERS: dict[str, Callable[..., Any]] = {
    "ok": ok,
    "error_503": error_503,
    "error_401_token_expired": error_401_token_expired,
    "oauth_full_flow": oauth_full_flow,
    "error_500_on_upload": error_500_on_upload,
}


def get_ai_stream_for_scenario(scenario: str, service: str = "claude") -> list[MockAIEvent]:
    """Resolve the AI handler for ``(scenario, service)`` and return its events.

    Raises whatever the handler raises (e.g. ``RuntimeError`` for error scenarios).
    Falls back to the default response if scenario/service is unknown.
    """
    from apps.core.mocks.scenarios import handler_for

    handler_name = handler_for(scenario, service)
    handler = AI_HANDLERS.get(handler_name)
    if handler is None:
        return canned_ai_stream()
    return handler()


def get_service_result(scenario: str, service: str, *args: Any, **kwargs: Any) -> Any:
    """Resolve the non-AI service handler for ``(scenario, service)`` and invoke it.

    For ``schwab/finnhub/files`` callers. Raises on error scenarios.
    """
    from apps.core.mocks.scenarios import handler_for

    handler_name = handler_for(scenario, service)
    handler = SERVICE_HANDLERS.get(handler_name, ok)
    return handler(*args, **kwargs)
