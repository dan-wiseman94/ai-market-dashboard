"""AIPrediction shares the core DirectionalCall + Resolution bases and claim() —
one "directional call + how it scored" domain, not two divergent copies (see
docs/superpowers/plans/2026-06-06-directional-call-consolidation.md).
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.observer.models import AIPrediction

pytestmark = pytest.mark.django_db


def test_aiprediction_claim_is_idempotent():
    now = timezone.now()
    pred = AIPrediction.objects.create(
        ticker="AAPL",
        direction="bullish",
        horizon_days=7,
        confidence=0.6,
        provider="claude",
        model="claude-opus-4-8",
        predicted_at=now,
        resolve_at=now,
    )
    assert pred.status == "open"

    assert AIPrediction.claim(pred.id, frm="open", to="resolving") is True
    pred.refresh_from_db()
    assert pred.status == "resolving"
    # a second claim from the original state loses (already moved)
    assert AIPrediction.claim(pred.id, frm="open", to="resolving") is False
