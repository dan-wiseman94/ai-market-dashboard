"""One-shot structured Claude run. Returns a parsed Pydantic model or raises.

Separate from the streaming ClaudeProvider so we don't mix two different
return contracts. Intended for Observer / trigger analyses where we want a
typed result in one go, not token streaming to the UI.

Uses anthropic>=0.96's native `messages.parse` which takes an `output_format`
Pydantic class and returns a `ParsedMessage` whose `.parsed_output` is an
instance of the same class.
"""

from __future__ import annotations

import logging
import time

from anthropic import Anthropic
from pydantic import BaseModel

from apps.ai.providers._config import client_kwargs

logger = logging.getLogger(__name__)


class StructuredParseError(RuntimeError):
    """Claude did not return parseable output for the requested schema."""


def run_structured[M: BaseModel](
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int = 2048,
    base_url: str = "",
) -> M:
    client = Anthropic(api_key=api_key, base_url=base_url or None, **client_kwargs())
    t0 = time.perf_counter()
    resp = client.messages.parse(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=max_tokens,
        output_format=output_model,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    parsed = resp.parsed_output
    if parsed is None:
        raise StructuredParseError(
            f"Claude did not return a parsed {output_model.__name__} output",
        )
    _record_structured_run(model=model, usage=getattr(resp, "usage", None), latency_ms=latency_ms)
    return parsed


def token_usage_from_anthropic(usage: object):
    """Map an Anthropic usage object to TokenUsage (total-input convention).

    input_tokens, cache_read, and cache_creation are disjoint in the API; sum
    them into input_tokens (the total prompt) and keep the read/write subsets so
    cost.py bills reads cheap and writes at the 1.25x premium. Mirrors the
    streaming ClaudeProvider accumulation.
    """
    from apps.ai.types import TokenUsage

    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    base = int(getattr(usage, "input_tokens", 0) or 0)
    return TokenUsage(
        input_tokens=base + read + write,
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cached_tokens=read,
        cache_write_tokens=write,
    )


def _record_structured_run(*, model: str, usage: object, latency_ms: int) -> None:
    """Best-effort: record this one-shot run as an AIRun so its cost counts
    against the provider caps. A ledger-write failure must never lose the
    already-parsed result, so we log and continue. Usage mapping mirrors the
    streaming ClaudeProvider (total input + read/write subsets).
    """
    from apps.ai.cost import record_ai_run

    try:
        record_ai_run(
            provider="claude",
            model=model,
            usage=token_usage_from_anthropic(usage),
            latency_ms=latency_ms,
        )
    except Exception:  # best-effort ledger write; the parsed result is already obtained
        logger.warning("run_structured: failed to record AIRun (model=%s)", model, exc_info=True)
