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
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)  # type: ignore[arg-type]

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        raw: list[dict[str, str]] = [
            {"role": "system", "content": req.system},
            *({"role": m.role, "content": m.content} for m in req.messages),
        ]
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
