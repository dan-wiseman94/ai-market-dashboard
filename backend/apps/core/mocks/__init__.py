"""Mock dispatch + scenario engine — loaded only when MOCK_EXTERNAL=true."""

from __future__ import annotations

from contextvars import ContextVar

from .providers import MockAIEvent, canned_ai_stream, is_mock_mode

__all__ = [
    "MockAIEvent",
    "canned_ai_stream",
    "current_scenario",
    "is_mock_mode",
    "reset_scenario",
    "run_service_scenario",
    "set_scenario",
]

_scenario: ContextVar[str] = ContextVar("e2e_scenario", default="default")


def set_scenario(name: str) -> None:
    _scenario.set(name)


def current_scenario() -> str:
    return _scenario.get()


def reset_scenario() -> None:
    _scenario.set("default")


def run_service_scenario(service: str):
    """Dispatch the active scenario's handler for a non-AI ``service``.

    Returns the handler result (e.g. canned oauth payload) and raises for
    error-injection scenarios (``news-503`` → 503, ``schwab-401`` → 401,
    ``files-upload-fail`` → 500). Resolves to the ``ok`` no-op under the default
    scenario. Callers gate on ``is_mock_mode()`` first, so this is inert in prod.
    """
    from .providers import get_service_result

    return get_service_result(current_scenario(), service)
