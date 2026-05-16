"""OpenAI provider — streams via openai SDK.

Also serves as the base for LocalProvider (see local.py) — the only difference
is base_url.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunRequest,
    TextDelta,
    TokenUsage,
    UsageEvent,
)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        if base_url:
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = AsyncOpenAI(api_key=api_key)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import current_scenario, is_mock_mode
        from apps.core.mocks.providers import get_ai_stream_for_scenario

        if is_mock_mode():
            try:
                events = get_ai_stream_for_scenario(current_scenario(), "openai")
            except Exception as exc:
                yield ErrorEvent(message=str(exc))
                return
            for ev in events:
                if ev.type == "text_delta":
                    yield TextDelta(text=ev.text)
                elif ev.type == "usage":
                    yield UsageEvent(
                        usage=TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0)
                    )
                elif ev.type == "error":
                    yield ErrorEvent(message=ev.text or "mock error")
                    return
                elif ev.type == "done":
                    yield DoneEvent()
                    return
            yield DoneEvent()
            return

        raw: list[dict] = [
            {"role": "system", "content": req.system},
        ]
        for m in req.messages:
            raw.append({"role": m.role, "content": _openai_content(m.content)})
        messages = cast(list[ChatCompletionMessageParam], raw)

        try:
            stream = await self._client.chat.completions.create(
                model=req.model,
                messages=messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
            usage_data = TokenUsage()
            async for chunk in stream:
                if getattr(chunk, "choices", None):
                    for choice in chunk.choices:
                        delta = getattr(choice, "delta", None)
                        text = getattr(delta, "content", None) if delta else None
                        if text:
                            yield TextDelta(text=text)
                u = getattr(chunk, "usage", None)
                if u is not None:
                    usage_data = TokenUsage(
                        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(u, "completion_tokens", 0) or 0,
                        cached_tokens=_cached(u),
                    )
            yield UsageEvent(usage=usage_data)
            yield DoneEvent()
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _cached(usage) -> int:
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    return getattr(details, "cached_tokens", 0) or 0


def _openai_content(content: str | list[dict]) -> str | list[dict]:
    """Normalize provider-shaped content to OpenAI's chat completion format.

    Text-only turns pass through as strings. Block lists already in OpenAI's
    `text`/`image_url` shape pass through. For each block lacking a `type`
    key, default to "text" with the raw string value.
    """
    if isinstance(content, str):
        return content
    out: list[dict] = []
    for block in content:
        if "type" in block:
            out.append(block)
            continue
        out.append({"type": "text", "text": str(block)})
    return out
