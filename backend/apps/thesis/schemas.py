"""Pydantic schema for structured post-mortem AI output.

Mirrors apps.observer.schemas: keep it tight. The deterministic verdict is
computed independently (apps.thesis.services.postmortem.objective_verdict);
``narrative_verdict`` here is the AI's own read and may disagree.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PostMortemReport(BaseModel):
    summary: str = Field(max_length=1200)
    what_worked: list[str] = Field(default_factory=list)
    what_missed: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    would_repeat: bool
    narrative_verdict: Literal["correct", "incorrect", "mixed", "inconclusive"]
