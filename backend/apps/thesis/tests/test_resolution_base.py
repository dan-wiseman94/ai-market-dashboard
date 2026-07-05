"""PostMortem shares the core Resolution base (forward_return_pct + verdict) and
its idempotent ``claim`` — the single home of the "directional call + how it
scored" domain (see docs/superpowers/plans/2026-06-06-directional-call-consolidation.md).
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.core.model_bases import Resolution
from apps.thesis.models import PostMortem, Thesis

pytestmark = pytest.mark.django_db


def test_postmortem_inherits_resolution():
    assert issubclass(PostMortem, Resolution)
    names = {f.name for f in PostMortem._meta.get_fields()}
    assert {"forward_return_pct", "verdict"} <= names  # provided by the base


def test_postmortem_claim_is_idempotent():
    thesis = Thesis.objects.create(title="x", ticker="X", direction="bullish")
    pm = PostMortem.objects.create(thesis=thesis, horizon_days=7, due_at=timezone.now())
    assert pm.status == "scheduled"

    assert PostMortem.claim(pm.id, frm="scheduled", to="running") is True
    pm.refresh_from_db()
    assert pm.status == "running"
    # a second claim from the original state loses (already moved)
    assert PostMortem.claim(pm.id, frm="scheduled", to="running") is False
