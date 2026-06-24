"""Pydantic schema for structured post-mortem AI output.

Mirrors apps.observer.schemas: keep it tight. This schema is prose + judgment
ONLY — the verdict is computed deterministically (and canonically) by
``apps.thesis.services.postmortem.objective_verdict`` over the same forward
return, so the AI is not asked to re-derive it (a parallel label could only
disagree with the authoritative one).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PostMortemReport(BaseModel):
    summary: str = Field(max_length=1200)
    what_worked: list[str] = Field(default_factory=list)
    what_missed: list[str] = Field(default_factory=list)
    lessons: list[str] = Field(default_factory=list)
    would_repeat: bool
