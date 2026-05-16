"""Cost-per-insight reports total spend and three insight counts + CPI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.analytics.services.cpi import cost_per_insight
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import AIRun, Message, Thread
from apps.triggers.models import EventTrigger, TriggerFiring


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="p", style="s")


def _aware(dt):
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _run(profile, *, cost: str, at: datetime, snap: Snapshot | None = None):
    thread = Thread.objects.create(kind="consult", profile=profile, pinned_snapshot=snap)
    m = Message.objects.create(thread=thread, role="assistant", content={"text": ""}, status="done")
    r = AIRun.objects.create(
        message=m,
        provider="claude",
        model="claude-opus-4-7",
        cost_usd=Decimal(cost),
        status="done",
    )
    AIRun.objects.filter(id=r.id).update(created_at=_aware(at))
    return r


def test_cpi_zero_when_no_runs(db, profile) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    result = cost_per_insight(
        start=now - timedelta(days=7),
        end=now + timedelta(days=1),
    )
    assert result["total_cost_usd"] == Decimal("0")
    assert result["insights"] == 0
    assert result["cost_per_insight_usd"] is None


def test_cpi_counts_distinct_threads_snapshots_trigger_fires(db, profile) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    snap = Snapshot.objects.create(profile=profile, status="ready", source="manual")
    _run(profile, cost="0.10", at=now - timedelta(hours=1), snap=snap)
    _run(profile, cost="0.05", at=now - timedelta(hours=1), snap=None)
    trig = EventTrigger.objects.create(profile=profile, name="t", condition={"all": []})
    thread = Thread.objects.create(kind="chat", profile=profile)
    firing = TriggerFiring.objects.create(trigger=trig, matched_values={}, thread=thread)
    TriggerFiring.objects.filter(id=firing.id).update(fired_at=now - timedelta(hours=2))
    _run(profile, cost="0.03", at=now - timedelta(hours=1), snap=None)

    out = cost_per_insight(
        start=now - timedelta(days=1),
        end=now + timedelta(days=1),
    )
    assert out["total_cost_usd"] == Decimal("0.18")
    assert out["threads_with_ai"] >= 3
    assert out["snapshots_with_ai"] == 1
    assert out["trigger_fires"] == 1
    assert (
        out["insights"] == out["threads_with_ai"] + out["snapshots_with_ai"] + out["trigger_fires"]
    )
    expected_cpi = out["total_cost_usd"] / out["insights"]
    assert out["cost_per_insight_usd"] == expected_cpi
