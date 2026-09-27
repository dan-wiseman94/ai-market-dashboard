"""Shared model bases (apps.core.model_bases): canonical vocab + abstract fields.

These bases model the shared "directional call + how it scored" domain
(thesis.PostMortem, observer.AIPrediction). They live in apps.core (the lowest
import layer) so thesis/observer depend DOWN on core, never up on analytics.
"""

from __future__ import annotations

from apps.core.model_bases import (
    DirectionalCall,
)


def test_directional_call_declares_call_fields():
    names = {f.name for f in DirectionalCall._meta.get_fields()}
    assert {
        "ticker",
        "direction",
        "horizon_days",
        "invalidation_price",
        "invalidation_note",
    } <= names
