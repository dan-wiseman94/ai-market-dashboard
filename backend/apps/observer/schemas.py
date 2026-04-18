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
