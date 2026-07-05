"""Pydantic schema for a structured coverage revision.

The AI is handed the prior house view plus the current situation and returns a
``CoverageRevisionDraft``. ``material_change`` is the hysteresis gate: the model
decides whether anything earned a revision, so the house view only churns when
there's a real reason — and that reason is recorded. Reaffirming (no change) is
a first-class, valid outcome, not a failure.

Mirrors ``apps/observer/schemas.py`` — keep it tight; add Optional-with-default
fields when extending, never remove.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Stance = Literal["bull", "bear", "neutral"]


class CoverageRevisionDraft(BaseModel):
    material_change: bool = Field(
        description="True only if something in the situation materially changed the "
        "house view (stance, conviction, the cases, or the levels you're watching). "
        "False to reaffirm the existing view unchanged — that is a valid answer.",
    )
    stance: Stance = Field(description="Your overall directional view on this ticker.")
    conviction: int = Field(
        ge=1,
        le=5,
        description="How strongly you hold the stance, 1 (tentative) to 5 (high conviction).",
    )
    bull_case: str = Field(description="The strongest case FOR upside, in a few sentences.")
    bear_case: str = Field(description="The strongest case AGAINST / for downside.")
    key_levels: dict = Field(
        default_factory=dict,
        description="Notable price levels as {label: price}, e.g. "
        '{"support": 520.0, "resistance": 535.0, "invalidation": 512.0}.',
    )
    watching_for: str = Field(
        description="The specific signal or event that would change this view.",
    )
    reason: str = Field(
        description="WHY the view changed (or, when reaffirming, why it still holds). "
        "This is the human-readable note on the revision.",
    )
