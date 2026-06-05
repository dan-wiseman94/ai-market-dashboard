"""N+1 regression gate for the observer-timeline aggregation.

observer_timeline() bins Messages per-day via a single grouped DB aggregation
(.values().annotate(Count)) then pure-Python zero-fills the gaps. Its query count
must be CONSTANT in the number of messages — a refactor that iterates messages and
touches msg.thread per row (a classic N+1) would breach this budget.

Uses pytest-django's django_assert_max_num_queries (Django-6.0 compatible); nplusone
is unmaintained and incompatible with Django 6.0 here. Mirrors the dashboard rollup
guard in apps/dashboard/tests/test_dashboard_query_budget.py.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.analytics.services.observer_timeline import observer_timeline
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread

# A single grouped aggregation query. 2 leaves headroom for a setup query while a
# per-row N+1 over the 30 seeded messages (≥30) would breach it decisively.
_QUERY_BUDGET = 2


@pytest.mark.django_db
def test_observer_timeline_is_query_bounded(django_assert_max_num_queries):
    prof = TradingProfile.objects.create(name="tl-prof", style="s")
    thread = Thread.objects.create(kind="observer", profile=prof, title="observer")
    for _ in range(30):
        Message.objects.create(
            thread=thread, role="assistant", content={"text": "x"}, status="done"
        )

    now = timezone.now()
    with django_assert_max_num_queries(_QUERY_BUDGET):
        out = observer_timeline(start=now - timedelta(days=1), end=now + timedelta(days=1))

    # The aggregation must still see all 30 (guard exercises the real grouped path, not an
    # empty window), proving the budget covers the populated case — not a vacuous 0-row one.
    assert sum(r["success"] for r in out) == 30
