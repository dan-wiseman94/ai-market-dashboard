"""Pydantic schemas for structured Observer outputs.

Keep these intentionally tight — the AI is free-form by default; structured
mode is opt-in on the schedule. Adding fields is backward-compatible; removing
them is not. When extending, add `Optional` with a default first, then make
required in a later release after running schedules have re-emitted.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Bias = Literal["bullish", "bearish", "neutral", "mixed"]


class KeyLevel(BaseModel):
    label: str = Field(description="Short label, e.g. 'prior day high'")
    price: float
    kind: Literal["support", "resistance", "pivot", "target"]


class Signal(BaseModel):
    ticker: str
    bias: Bias
    thesis: str = Field(max_length=500)
    invalidation: str = Field(max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)


class ObservationReport(BaseModel):
    headline: str = Field(max_length=140)
    bias: Bias
    summary: str = Field(max_length=1200)
    signals: list[Signal] = Field(default_factory=list, max_length=10)
    key_levels: list[KeyLevel] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=8)
    next_check_in: str = Field(
        max_length=80,
        description="When or under what condition the observer should re-check.",
    )
    predicted_direction: Literal["bullish", "bearish", "neutral"] | None = Field(
        default=None,
        description="Your single directional call for the primary ticker over the horizon, if any.",
    )
    predicted_horizon_days: int | None = Field(
        default=None,
        description="Horizon in trading days for predicted_direction.",
    )
    grounding: list[str] = Field(
        default_factory=list,
        max_length=12,
        description="Which provided data sections each key claim used (e.g. 'quotes', 'chain analytics').",
    )


class ProviderTake(BaseModel):
    """One model's structured opinion in a consensus run."""

    provider: str
    model: str
    bias: Bias
    signal_bias: dict[str, Bias] = Field(
        default_factory=dict,
        description="Per-ticker directional call lifted from this take's signals.",
    )


class ConsensusReport(BaseModel):
    """Cross-model agreement signal.

    Fans the same ObservationReport prompt across several structured-capable
    (provider, model) pairs and measures whether they agree. Agreement is a
    confidence signal a single model can't give; divergence is an explicit
    'do more homework' flag. Degrades honestly to a single-provider result
    rather than fabricating a consensus.
    """

    n_providers: int
    bias_agreement: float | None = Field(
        default=None,
        description="Fraction of takes agreeing with the modal overall bias; "
        "None when fewer than 2 takes (no consensus possible).",
    )
    modal_bias: Bias | None = Field(
        default=None,
        description="Most common overall bias across takes; the single one (or "
        "None) when fewer than 2 takes.",
    )
    divergent: bool = Field(
        default=False,
        description="True when takes disagree on the overall bias.",
    )
    per_ticker: dict[str, dict] = Field(
        default_factory=dict,
        description="ticker -> {agreement, modal, takes:{provider:bias}} across takes.",
    )
    takes: list[ProviderTake] = Field(default_factory=list)
    note: str = Field(
        default="",
        description="Human-readable caveat, e.g. 'single provider — no consensus available'.",
    )
