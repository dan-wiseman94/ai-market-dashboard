"""Trigger heatmap buckets TriggerFiring.fired_at by (weekday, hour_of_day)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.analytics.services.trigger_heatmap import trigger_heatmap
from apps.observer.models import EventTrigger, TriggerFiring
from apps.profiles.models import TradingProfile


@pytest.fixture
def trigger(db):
    prof = TradingProfile.objects.create(name="p", style="s")
    return EventTrigger.objects.create(profile=prof, name="t", condition={"all": []})


def _fire_at(trig, when: datetime) -> None:
    f = TriggerFiring.objects.create(trigger=trig, matched_values={})
    TriggerFiring.objects.filter(id=f.id).update(fired_at=when)


def test_heatmap_has_168_cells(db, trigger) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    cells = trigger_heatmap(
        start=now - timedelta(days=7),
        end=now + timedelta(days=1),
    )
    assert len(cells) == 7 * 24
    assert {c["weekday"] for c in cells} == set(range(7))
    assert {c["hour"] for c in cells} == set(range(24))


def test_heatmap_counts_fires_in_correct_bucket(db, trigger) -> None:
    mon_1430 = datetime(2026, 4, 6, 14, 30, tzinfo=UTC)
    _fire_at(trigger, mon_1430)
    _fire_at(trigger, mon_1430 + timedelta(minutes=15))

    thu_0905 = datetime(2026, 4, 9, 9, 5, tzinfo=UTC)
    _fire_at(trigger, thu_0905)

    cells = trigger_heatmap(
        start=datetime(2026, 4, 1, tzinfo=UTC),
        end=datetime(2026, 4, 15, tzinfo=UTC),
    )
    by_key = {(c["weekday"], c["hour"]): c["count"] for c in cells}
    assert by_key[(0, 14)] == 2
    assert by_key[(3, 9)] == 1
    assert by_key[(5, 3)] == 0


def test_heatmap_respects_window(db, trigger) -> None:
    outside = datetime(2026, 4, 1, tzinfo=UTC)
    _fire_at(trigger, outside)
    cells = trigger_heatmap(
        start=datetime(2026, 4, 5, tzinfo=UTC),
        end=datetime(2026, 4, 15, tzinfo=UTC),
    )
    assert sum(c["count"] for c in cells) == 0
