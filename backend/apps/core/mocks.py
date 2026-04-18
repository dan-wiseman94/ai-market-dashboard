"""Deterministic external-API mocks (activated when MOCK_EXTERNAL=true)."""
from __future__ import annotations

import os
from dataclasses import dataclass


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
