"""One-shot structured run against an OpenAI-compatible chat endpoint.

Returns a parsed Pydantic model or raises. Serves both the ``openai`` provider
and ``local`` (any OpenAI-compatible server). ``chat.completions.parse`` sends
the model's JSON schema as a strict ``response_format``; a local server that
rejects strict schemas falls back once to ``json_object`` mode with the schema
in the prompt, validated client-side. The result is always schema-validated.

Separate from the streaming ``OpenAIProvider`` so the two return contracts
(typed one-shot vs event stream) stay apart. Records an ``AIRun`` under the
real provider name so cost caps see the spend (``local`` costs $0).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import cast

from openai import BadRequestError, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ParsedChatCompletion
from pydantic import BaseModel, ValidationError

from apps.ai.providers._config import client_kwargs
from apps.ai.providers.claude_structured import StructuredParseError

logger = logging.getLogger(__name__)

# The SDK demands a key at construction; local servers ignore it (mirrors LocalProvider).
_PLACEHOLDER_KEY = "sk-local-placeholder"
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def run_structured[M: BaseModel](
    *,
    provider: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int = 2048,
    base_url: str = "",
) -> M:
    client = OpenAI(
        api_key=api_key or _PLACEHOLDER_KEY, base_url=base_url or None, **client_kwargs()
    )
    t0 = time.perf_counter()
    completion: ChatCompletion
    try:
        parsed_completion = _parse(client, provider, model, system, user, output_model, max_tokens)
        completion = parsed_completion
        parsed = _parsed_or_raise(parsed_completion, output_model)
    except BadRequestError:
        if provider != "local":
            raise
        completion, parsed = _local_fallback(
            client,
            model=model,
            system=system,
            user=user,
            output_model=output_model,
            max_tokens=max_tokens,
        )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    _record_structured_run(
        provider=provider, model=model, usage=completion.usage, latency_ms=latency_ms
    )
    return parsed


def _parse[M: BaseModel](
    client: OpenAI,
    provider: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int,
) -> ParsedChatCompletion[M]:
    """Strict-schema parse. ``max_completion_tokens`` is the current OpenAI parameter;
    older OpenAI-compatible local servers only know ``max_tokens``."""
    if provider == "local":
        return client.chat.completions.parse(
            model=model,
            messages=_messages(system, user),
            response_format=output_model,
            max_tokens=max_tokens,
        )
    return client.chat.completions.parse(
        model=model,
        messages=_messages(system, user),
        response_format=output_model,
        max_completion_tokens=max_tokens,
    )


def _messages(system: str, user: str) -> list[ChatCompletionMessageParam]:
    raw: list[dict[str, str]] = []
    if system:
        raw.append({"role": "system", "content": system})
    raw.append({"role": "user", "content": user})
    return cast(list[ChatCompletionMessageParam], raw)


def _parsed_or_raise[M: BaseModel](completion: ParsedChatCompletion[M], output_model: type[M]) -> M:
    if not completion.choices:
        raise StructuredParseError(f"No choices returned for {output_model.__name__}")
    message = completion.choices[0].message
    if message.refusal:
        raise StructuredParseError(f"Model refused {output_model.__name__}: {message.refusal}")
    if message.parsed is None:
        raise StructuredParseError(f"Model did not return a parsed {output_model.__name__} output")
    return message.parsed


def _local_fallback[M: BaseModel](
    client: OpenAI,
    *,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int,
) -> tuple[ChatCompletion, M]:
    """``json_object`` mode with the schema in the prompt, validated client-side."""
    schema = json.dumps(output_model.model_json_schema(), separators=(",", ":"))
    instruction = (
        "Respond with a single JSON object and nothing else (no prose, no code fences). "
        f"The JSON must match this JSON schema:\n{schema}"
    )
    system_text = f"{system}\n\n{instruction}" if system else instruction
    completion = client.chat.completions.create(
        model=model,
        messages=_messages(system_text, user),
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    content = completion.choices[0].message.content if completion.choices else None
    text = _FENCE.sub("", content or "").strip()
    try:
        parsed = output_model.model_validate_json(text)
    except ValidationError as exc:
        raise StructuredParseError(
            f"Local fallback returned JSON that does not match {output_model.__name__}: {exc}"
        ) from exc
    return completion, parsed


def token_usage_from_openai(usage: object):
    """Map an OpenAI usage object to TokenUsage. ``prompt_tokens`` is the total prompt;
    ``prompt_tokens_details.cached_tokens`` is the cached subset. Mirrors the streaming
    ``OpenAIProvider`` accumulation."""
    from apps.ai.types import TokenUsage

    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
    return TokenUsage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        cached_tokens=cached,
        cache_write_tokens=0,
    )


def _record_structured_run(*, provider: str, model: str, usage: object, latency_ms: int) -> None:
    """Best-effort: record this one-shot run as an AIRun so its cost counts against
    the provider caps. A ledger-write failure must never lose the already-parsed
    result, so we log and continue."""
    from apps.ai.cost import record_ai_run

    try:
        record_ai_run(
            provider=provider,
            model=model,
            usage=token_usage_from_openai(usage),
            latency_ms=latency_ms,
        )
    except Exception:  # best-effort ledger write; the parsed result is already obtained
        logger.warning(
            "run_structured: failed to record AIRun (provider=%s model=%s)",
            provider,
            model,
            exc_info=True,
        )
