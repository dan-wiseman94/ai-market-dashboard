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
    # A reasoning model needs room to answer: 16k clears any observation-length
    # response, keeps a legacy `budget_tokens` (<= 8k) strictly below it as the API
    # requires, and stays modest enough for a local OpenAI-compatible endpoint.
    max_tokens: int = 16_000
    temperature: float = 1.0
    cache_system: bool = True
    cache_last_message: bool = False
    tools: list[dict] = field(default_factory=list)
    enable_thinking: bool = False
    # Reasoning depth: "low"/"medium"/"high"/"xhigh"/"max". "" omits the parameter
    # and takes the API default. Clamped per model by `catalog.resolve_effort`.
    effort: str = ""
    # Thinking token ceiling for the models that still take the budget shape; the
    # adaptive rows reject it. Ignored unless `enable_thinking` is set.
    thinking_budget: int = 0
    memory_dir: str = ""  # "" disables Memory tool
    max_tool_iterations: int = 0  # 0 = unlimited; >0 bounds the tool loop


@dataclass
class TokenUsage:
    # input_tokens is the TOTAL prompt size; cached_tokens (cache reads) and
    # cache_write_tokens (cache creation) are non-overlapping SUBSETS of it,
    # billed at the cheap read rate and the write premium respectively.
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0


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


@dataclass
class CitationEvent:
    """One citation the model attached to the text it just streamed.

    The Anthropic location variants are NOT uniform: a `search_result` citation
    carries `source`+`title`, a web-search one `url`+`title`, and a document one
    (char/page/content-block, from a Files-API attach) neither — only
    `document_title`. `source` is "" for a document citation; `location` keeps the
    raw variant so a consumer can tell them apart.
    """

    type: Literal["citation"] = "citation"
    location: str = ""
    source: str = ""
    title: str = ""
    cited_text: str = ""


RunEvent = (
    TextDelta
    | UsageEvent
    | DoneEvent
    | ErrorEvent
    | ToolCallEvent
    | ToolResultEvent
    | ThinkingDeltaEvent
    | CitationEvent
)
