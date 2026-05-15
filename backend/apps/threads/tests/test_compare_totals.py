"""Sanity: AIRun rows sum correctly across branches for a single parent."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db.models import Max, Sum

from apps.threads.models import AIRun, Message, Thread


@pytest.mark.django_db
def test_compare_totals_aggregation() -> None:
    thread = Thread.objects.create(kind="chat", title="t")
    parent = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": "hi"},
        status="done",
    )
    # three branches
    costs = [Decimal("0.0100"), Decimal("0.0080"), Decimal("0.0068")]
    durations = [1200, 1800, 1500]
    for cost, dur in zip(costs, durations, strict=True):
        m = Message.objects.create(
            thread=thread,
            role="assistant",
            content={"text": "r"},
            status="done",
            parent_message_id=parent.id,
        )
        AIRun.objects.create(
            message=m,
            provider="claude",
            model="claude-sonnet-4-6",
            cost_usd=cost,
            latency_ms=dur,
            status="done",
        )

    agg = AIRun.objects.filter(message__parent_message_id=parent.id).aggregate(
        total=Sum("cost_usd"),
        slowest=Max("latency_ms"),
    )
    assert agg["total"] == sum(costs)
    assert agg["slowest"] == max(durations)
