"""N+1 regression gate for the dashboard rollup.

The command-centre aggregator (GET /api/dashboard/) must run in a bounded number
of queries that does NOT scale with row count. We seed several rows per section
and assert a tight query budget — an introduced N+1 (a per-row query) would breach
it. Uses pytest-django's django_assert_max_num_queries (Django-6.0 compatible),
not nplusone (unmaintained; incompatible with Django 6.0 here).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.observer.models import EventTrigger, TriggerFiring
from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis

# Clean count is 15 with the seeded rows — and it's constant in row count (no N+1).
# 18 leaves small headroom for legitimate changes while a per-row N+1 (≥8 here) breaches it.
_QUERY_BUDGET = 18


@pytest.mark.django_db
def test_dashboard_rollup_is_query_bounded(django_assert_max_num_queries):
    profile = TradingProfile.objects.create(name="budget-prof", style="s")
    for i in range(8):
        Thesis.objects.create(
            title=f"Thesis {i}",
            ticker=f"TK{i}",
            direction="bullish",
            target_price=Decimal("150"),
            invalidation_price=Decimal("90"),
            status="open",
            profile=profile,
        )
    for i in range(5):
        trigger = EventTrigger.objects.create(
            profile=profile, name=f"trig-{i}", condition={"all": []}, enabled=True
        )
        for _ in range(3):
            TriggerFiring.objects.create(trigger=trigger, matched_values={"price": 100})

    client = APIClient()
    with django_assert_max_num_queries(_QUERY_BUDGET):
        r = client.get("/api/dashboard/")
    assert r.status_code == 200
