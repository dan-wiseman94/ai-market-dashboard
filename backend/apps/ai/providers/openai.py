"""OpenAI provider — streams via openai SDK, loops on tool_calls.

Also serves as the base for LocalProvider (see local.py) — the only difference
is base_url.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from apps.ai.providers._config import client_kwargs
from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunRequest,
    TextDelta,
    TokenUsage,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        from apps.core.mocks import is_mock_mode

        # Under MOCK_EXTERNAL, run() short-circuits to canned events and never calls
        # the SDK — but AsyncOpenAI() still demands a key at construction. E2E seeds
        # no key, so supply a placeholder to let the provider construct (and thus be
        # exercisable) in mock mode. Never used for a real request.
        if not api_key and is_mock_mode():
            api_key = "mock-no-key"
        kw = client_kwargs()
        if base_url:
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, **kw)
        else:
            self._client = AsyncOpenAI(api_key=api_key, **kw)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import is_mock_mode

        if is_mock_mode():
            from apps.ai.providers._mock import mock_run

            async for ev in mock_run("openai"):
                yield ev
            return

        raw: list[dict] = [{"role": "system", "content": req.system}]
        for m in req.messages:
            raw.append({"role": m.role, "content": _openai_content(m.content)})

        total_in = total_out = total_cached = 0

        try:
            while True:
                create_kwargs: dict = dict(
                    model=req.model,
                    messages=cast(list[ChatCompletionMessageParam], raw),
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                if req.tools:
                    create_kwargs["tools"] = req.tools

                stream = await self._client.chat.completions.create(**create_kwargs)

                iter_text = ""
                tool_acc: dict[int, dict] = {}
                finish_reason: str | None = None

                async for chunk in stream:
                    for choice in getattr(chunk, "choices", None) or []:
                        delta = getattr(choice, "delta", None)
                        if delta is not None:
                            text = getattr(delta, "content", None)
                            if text:
                                iter_text += text
                                yield TextDelta(text=text)
                            for tc in getattr(delta, "tool_calls", None) or []:
                                slot = tool_acc.setdefault(
                                    tc.index, {"id": "", "name": "", "args": ""}
                                )
                                if getattr(tc, "id", None):
                                    slot["id"] = tc.id
                                fn = getattr(tc, "function", None)
                                if fn is not None:
                                    if getattr(fn, "name", None):
                                        slot["name"] = fn.name
                                    if getattr(fn, "arguments", None):
                                        slot["args"] += fn.arguments
                        if getattr(choice, "finish_reason", None):
                            finish_reason = choice.finish_reason
                    u = getattr(chunk, "usage", None)
                    if u is not None:
                        total_in += getattr(u, "prompt_tokens", 0) or 0
                        total_out += getattr(u, "completion_tokens", 0) or 0
                        total_cached += _cached(u)

                if finish_reason != "tool_calls" or not tool_acc:
                    break

                # Reconstruct the assistant tool_calls turn for the next request.
                ordered = [tool_acc[i] for i in sorted(tool_acc)]
                raw.append(
                    {
                        "role": "assistant",
                        "content": iter_text or None,
                        "tool_calls": [
                            {
                                "id": s["id"],
                                "type": "function",
                                "function": {"name": s["name"], "arguments": s["args"]},
                            }
                            for s in ordered
                        ],
                    }
                )

                toolset = _resolve_toolset()
                for s in ordered:
                    try:
                        parsed = json.loads(s["args"] or "{}")
                    except json.JSONDecodeError as exc:
                        # Malformed args: skip the toolset call, surface an error
                        # result, and let the loop advance to the next round.
                        parsed = {}
                        outcome = {
                            "ok": False,
                            "error": f"Invalid tool arguments JSON: {exc} (raw: {s['args']!r})",
                        }
                        latency_ms = 0
                    else:
                        t0 = time.perf_counter()
                        outcome = toolset.run(s["name"], parsed)
                        latency_ms = int((time.perf_counter() - t0) * 1000)

                    yield ToolCallEvent(tool_use_id=s["id"], name=s["name"], input=parsed)
                    yield ToolResultEvent(
                        tool_use_id=s["id"],
                        ok=bool(outcome.get("ok")),
                        result=outcome.get("result"),
                        error=str(outcome.get("error", "")),
                        latency_ms=latency_ms,
                    )
                    raw.append(
                        {
                            "role": "tool",
                            "tool_call_id": s["id"],
                            "content": str(
                                outcome.get("result") if outcome.get("ok") else outcome.get("error")
                            ),
                        }
                    )

            yield UsageEvent(
                usage=TokenUsage(
                    input_tokens=total_in,
                    output_tokens=total_out,
                    cached_tokens=total_cached,
                )
            )
            yield DoneEvent()
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")

    async def list_models(self, *, timeout: float = 10.0) -> list[str]:
        """List model ids the endpoint serves (GET /v1/models).

        Doubles as a reachability + OpenAI-compatibility probe. Honors
        MOCK_EXTERNAL like run() so e2e/mock runs never touch the network.
        """
        from apps.core.mocks import is_mock_mode

        if is_mock_mode():
            return ["local-7b", "local-13b"]
        page = await self._client.with_options(timeout=timeout).models.list()
        return sorted(m.id for m in page.data)


def _resolve_toolset():
    """Late import so tests can patch without importing market services."""
    from apps.ai.tools.registry import default_toolset

    return default_toolset()


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
