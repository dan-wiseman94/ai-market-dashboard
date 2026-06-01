"""Persona advocates. Each runs synchronously via claude_structured (Claude-only
in v1). Multi-provider voice assignment is deferred to v2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.ai.providers.claude_structured import run_structured
from apps.warroom import constants as C

_FRAMING = {
    "bull": "You are the BULL. Argue the strongest evidence-based case FOR the position. Be concrete.",
    "bear": "You are the BEAR. Argue the strongest evidence-based case AGAINST the position. Be concrete.",
    "skeptic": "You are the SKEPTIC. Attack the assumptions on BOTH sides; name what's unknowable and what would falsify each case.",
}


class PersonaArgument(BaseModel):
    argument: str = Field(description="The persona's case, 3-6 sentences.")
    key_points: list[str] = Field(default_factory=list, description="2-4 bullet takeaways.")


def _user_prompt(subject_context: str, prior_args: list[dict]) -> str:
    parts = [f"SUBJECT:\n{subject_context}"]
    if prior_args:
        prior = "\n".join(f"- [{a.get('persona')}] {a.get('argument')}" for a in prior_args)
        parts.append(f"\nARGUMENTS SO FAR (rebut where you disagree):\n{prior}")
    parts.append("\nMake your case. Strictly observational; no buy/sell directive.")
    return "\n".join(parts)


def run_persona(persona: str, subject_context: str, prior_args: list[dict], *, api_key: str, model: str, base_url: str) -> PersonaArgument:
    return run_structured(
        api_key=api_key, model=model, system=_FRAMING[persona],
        user=_user_prompt(subject_context, prior_args), output_model=PersonaArgument,
        max_tokens=C.PERSONA_MAX_TOKENS, base_url=base_url,
    )
