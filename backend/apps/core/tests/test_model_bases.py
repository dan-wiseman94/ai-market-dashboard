"""Shared model bases (apps.core.model_bases): canonical vocab + abstract fields.

These bases model the shared "directional call + how it scored" domain
(thesis.PostMortem, observer.AIPrediction). They live in apps.core (the lowest
import layer) so thesis/observer depend DOWN on core, never up on analytics.
"""

from __future__ import annotations

from apps.core.model_bases import (
    DIRECTION_CHOICES,
    VERDICT_CHOICES,
    DirectionalCall,
    Resolution,
    TimeStamped,
)


def test_verdict_choices_are_canonical():
    assert [c[0] for c in VERDICT_CHOICES] == ["correct", "incorrect", "mixed", "inconclusive"]


def test_direction_choices_are_canonical():
    assert [c[0] for c in DIRECTION_CHOICES] == ["bullish", "bearish", "neutral"]


def test_bases_are_abstract():
    assert TimeStamped._meta.abstract
    assert DirectionalCall._meta.abstract
    assert Resolution._meta.abstract


def test_resolution_declares_outcome_fields():
    names = {f.name for f in Resolution._meta.get_fields()}
    assert {"forward_return_pct", "verdict"} <= names


def test_directional_call_declares_call_fields():
    names = {f.name for f in DirectionalCall._meta.get_fields()}
    assert {
        "ticker",
        "direction",
        "horizon_days",
        "invalidation_price",
        "invalidation_note",
    } <= names
