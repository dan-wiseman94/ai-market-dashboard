import pytest

from apps.observer.models import EventTrigger, TriggerFiring
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread


@pytest.mark.django_db
def test_trigger_firing_minimal():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    f = TriggerFiring.objects.create(
        trigger=t,
        matched_values={"price:SPY": 551.2},
    )
    assert f.cost_capped is False
    assert f.snapshot is None
    assert f.thread is None
    assert f.fired_at is not None


@pytest.mark.django_db
def test_trigger_firing_with_refs():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    snap = Snapshot.objects.create(profile=p, includes=[])
    thread = Thread.objects.create(kind="chat", profile=p, title="t")
    f = TriggerFiring.objects.create(
        trigger=t,
        matched_values={},
        snapshot=snap,
        thread=thread,
    )
    assert f.snapshot_id == snap.id
    assert f.thread_id == thread.id


@pytest.mark.django_db
def test_trigger_firing_deleted_on_trigger_cascade():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={})
    t.delete()
    assert TriggerFiring.objects.count() == 0
