"""Synthesizer: read the persona arguments, return a structured verdict."""

from __future__ import annotations

from pydantic import BaseModel, Field

from apps.ai.providers.claude_structured import run_structured
from apps.warroom import constants as C

_SYSTEM = (
    "You are the SYNTHESIZER presiding over a bull/bear/skeptic debate. Weigh the arguments and "
    "return a balanced verdict + a calibrated confidence. Strictly observational; no buy/sell directive."
)


class WarRoomVerdict(BaseModel):
    verdict: str = Field(description="One-line verdict, e.g. 'bull case stronger' / 'balanced'.")
    confidence: float = Field(ge=0, le=1, description="Confidence in the verdict, 0-1.")
    strongest_bull: str = Field(description="The single strongest bull point.")
    strongest_bear: str = Field(description="The single strongest bear point.")
    what_would_change_my_mind: str = Field(description="The key falsifier.")


def synthesize(subject_context: str, persona_args: list[dict], *, api_key: str, model: str, base_url: str) -> WarRoomVerdict:
    args = "\n".join(f"- [{a.get('persona')}] {a.get('argument')}" for a in persona_args)
    user = f"SUBJECT:\n{subject_context}\n\nARGUMENTS:\n{args}\n\nDeliver your verdict."
    return run_structured(
        api_key=api_key, model=model, system=_SYSTEM, user=user,
        output_model=WarRoomVerdict, max_tokens=C.VERDICT_MAX_TOKENS, base_url=base_url,
    )
