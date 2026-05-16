"""Shared types for the AI provider layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RoleType = Literal["user", "assistant", "system"]


@dataclass
class ChatMessage:
    role: RoleType
    # str for text-only turns; list[dict] for provider-shaped content blocks
    # (Claude: `{"type": "image", "source": ...}`, OpenAI: `{"type": "image_url", ...}`).
    content: str | list[dict]


@dataclass
class RunRequest:
    model: str
    system: str
    messages: list[ChatMessage]
    max_tokens: int = 4096
    temperature: float = 1.0
    cache_system: bool = True
    cache_last_message: bool = False
    tools: list[dict] = field(default_factory=list)
    thinking_budget: int = 0  # 0 disables extended thinking
    memory_dir: str = ""  # "" disables Memory tool


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


@dataclass
class ToolCallEvent:
    type: Literal["tool_call"] = "tool_call"
    tool_use_id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class ToolResultEvent:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    ok: bool = True
    result: object = None
    error: str = ""
    latency_ms: int = 0


@dataclass
class ThinkingDeltaEvent:
    type: Literal["thinking_delta"] = "thinking_delta"
    text: str = ""


RunEvent = (
    TextDelta
    | UsageEvent
    | DoneEvent
    | ErrorEvent
    | ToolCallEvent
    | ToolResultEvent
    | ThinkingDeltaEvent
)
