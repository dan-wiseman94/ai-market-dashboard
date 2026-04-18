"""Shared types for the AI provider layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoleType = Literal["user", "assistant", "system"]


@dataclass
class ChatMessage:
    role: RoleType
    content: str


@dataclass
class RunRequest:
    model: str
    system: str
    messages: list[ChatMessage]
    max_tokens: int = 4096
    temperature: float = 1.0
    cache_system: bool = True
    cache_last_message: bool = False


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class CostEstimate:
    low: float
    high: float
    model: str


@dataclass
class TextDelta:
    type: Literal["text_delta"] = "text_delta"
    text: str = ""


@dataclass
class UsageEvent:
    type: Literal["usage"] = "usage"
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass
class DoneEvent:
    type: Literal["done"] = "done"


@dataclass
class ErrorEvent:
    type: Literal["error"] = "error"
    message: str = ""


RunEvent = TextDelta | UsageEvent | DoneEvent | ErrorEvent
