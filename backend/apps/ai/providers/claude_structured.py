"""One-shot structured Claude run. Returns a parsed Pydantic model or raises.

Separate from the streaming ClaudeProvider so we don't mix two different
return contracts. Intended for Observer / trigger analyses where we want a
typed result in one go, not token streaming to the UI.

Uses anthropic>=0.96's native `messages.parse` which takes an `output_format`
Pydantic class and returns a `ParsedMessage` whose `.parsed_output` is an
instance of the same class.
"""
from __future__ import annotations

from anthropic import Anthropic
from pydantic import BaseModel


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
    client = Anthropic(api_key=api_key, base_url=base_url or None)
    resp = client.messages.parse(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=max_tokens,
        output_format=output_model,
    )
    parsed = resp.parsed_output
    if parsed is None:
        raise StructuredParseError(
            f"Claude did not return a parsed {output_model.__name__} output",
        )
    return parsed
