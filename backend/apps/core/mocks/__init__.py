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
    "set_scenario",
]

_scenario: ContextVar[str] = ContextVar("e2e_scenario", default="default")


def set_scenario(name: str) -> None:
    _scenario.set(name)


def current_scenario() -> str:
    return _scenario.get()


def reset_scenario() -> None:
    _scenario.set("default")
