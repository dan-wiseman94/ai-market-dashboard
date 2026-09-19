"""One-shot structured run against an OpenAI-compatible chat endpoint.

Returns a parsed Pydantic model or raises. Serves both the ``openai`` provider
and ``local`` (any OpenAI-compatible server). The request carries a sanitized
strict JSON schema (OpenAI's strict mode rejects ``minLength``/``maxLength``;
the sanitizer folds those into the field description, and the reply is
validated client-side against the full Pydantic model, which still enforces
them). A local server that rejects strict schemas falls back once to
``json_object`` mode with the schema in the prompt, validated the same way.

Separate from the streaming ``OpenAIProvider`` so the two return contracts
(typed one-shot vs event stream) stay apart. Records an ``AIRun`` under the
real provider name so cost caps see the spend (``local`` costs $0).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any, cast

from openai import BadRequestError, OpenAI
from openai.lib._pydantic import (
    to_strict_json_schema,  # SDK-private; pinned by uv.lock, fails loudly on an SDK upgrade that moves it
)
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from apps.ai.providers._config import client_kwargs
from apps.ai.providers.claude_structured import StructuredParseError

if TYPE_CHECKING:
    from apps.ai.types import TokenUsage

logger = logging.getLogger(__name__)

# The SDK demands a key at construction; local servers ignore it (mirrors LocalProvider).
_PLACEHOLDER_KEY = "sk-local-placeholder"
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")

# JSON-Schema keywords OpenAI strict mode accepts (structural + the documented constraint subset).
_STRICT_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "enum",
        "const",
        "$defs",
        "$ref",
        "description",
        "title",
        "pattern",
        "format",
        "multipleOf",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
    }
)
_DESCRIBED_CONSTRAINTS = ("minLength", "maxLength")


def strict_schema_for(output_model: type[BaseModel]) -> dict[str, Any]:
    """The JSON schema sent to OpenAI: the SDK's strict conversion (every property
    required, ``additionalProperties`` off) with the string-length constraints the API
    rejects moved into the field description. Pydantic validates the reply against the
    full model, so the constraints are still enforced client-side."""
    return _sanitize(to_strict_json_schema(output_model))


def _sanitize(node: Any) -> Any:
    """Drop every schema keyword outside ``_STRICT_KEYWORDS``, recursing through
    ``items``, ``anyOf`` members, and ``$defs`` entries alike. ``properties`` and
    ``$defs`` values are name-keyed maps (field/def name → schema), not schema
    nodes themselves, so their keys are never filtered — only their values are
    recursively sanitized. A dropped length constraint is preserved as a
    description note so the field's documented bound survives even though the
    API never sees the keyword."""
    if isinstance(node, list):
        return [_sanitize(n) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    notes = [f"{k} {node[k]}" for k in _DESCRIBED_CONSTRAINTS if k in node]
    for key, value in node.items():
        if key in _DESCRIBED_CONSTRAINTS or key not in _STRICT_KEYWORDS:
            continue
        if key in ("properties", "$defs") and isinstance(value, dict):
            out[key] = {name: _sanitize(sub_schema) for name, sub_schema in value.items()}
        else:
            out[key] = _sanitize(value)
    if notes:
        desc = str(out.get("description", "")).strip()
        out["description"] = f"{desc} ({', '.join(notes)})".strip()
    return out


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
        completion = client.chat.completions.create(
            **_request_kwargs(provider, model, system, user, output_model, max_tokens)
        )
        parsed = _validate_completion(completion, output_model)
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


def _request_kwargs(
    provider: str,
    model: str,
    system: str,
    user: str,
    output_model: type[BaseModel],
    max_tokens: int,
) -> dict[str, Any]:
    """The strict-schema request. ``max_completion_tokens`` is the current OpenAI
    parameter; older OpenAI-compatible local servers only know ``max_tokens``."""
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=_messages(system, user),
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": output_model.__name__,
                "schema": strict_schema_for(output_model),
                "strict": True,
            },
        },
    )
    if provider == "local":
        kwargs["max_tokens"] = max_tokens
    else:
        kwargs["max_completion_tokens"] = max_tokens
    return kwargs


def _messages(system: str, user: str) -> list[ChatCompletionMessageParam]:
    raw: list[dict[str, str]] = []
    if system:
        raw.append({"role": "system", "content": system})
    raw.append({"role": "user", "content": user})
    return cast(list[ChatCompletionMessageParam], raw)


def _validate_completion[M: BaseModel](completion: ChatCompletion, output_model: type[M]) -> M:
    """Reject an unusable strict-mode reply before validating its content: no
    choices, an explicit refusal, or a length-truncated response each get their
    own diagnostic rather than surfacing as a generic JSON-validation failure."""
    if not completion.choices:
        raise StructuredParseError(f"No choices returned for {output_model.__name__}")
    choice = completion.choices[0]
    message = choice.message
    if message.refusal:
        raise StructuredParseError(f"Model refused {output_model.__name__}: {message.refusal}")
    if choice.finish_reason == "length":
        raise StructuredParseError(f"{output_model.__name__} response was truncated at max_tokens")
    return _validate_content(message.content, output_model)


def _validate_content[M: BaseModel](content: str | None, output_model: type[M]) -> M:
    """Strip any code fence and validate the reply text against ``output_model``.
    Shared by the strict path and the local ``json_object`` fallback so both
    enforce the schema identically."""
    text = _FENCE.sub("", content or "").strip()
    try:
        return output_model.model_validate_json(text)
    except ValidationError as exc:
        raise StructuredParseError(
            f"Response does not match {output_model.__name__}: {exc}"
        ) from exc


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
    return completion, _validate_content(content, output_model)


def token_usage_from_openai(usage: object) -> TokenUsage:
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
