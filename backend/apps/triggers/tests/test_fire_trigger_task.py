from decimal import Decimal
from unittest.mock import patch

import fakeredis
import pytest

from apps.ai.cost import CostCapExceededError
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.triggers.models import EventTrigger, TriggerFiring


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.tasks._redis", return_value=client):
        yield client


@pytest.fixture
def provider_cfg(db):
    from apps.secrets.models import ProviderConfig
    cfg, _ = ProviderConfig.objects.update_or_create(
        provider="claude",
        defaults={"daily_cost_cap_usd": Decimal("10.00"), "enabled": True},
    )
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.mark.django_db
def test_fire_trigger_happy_path(fake_redis, provider_cfg):
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="SPY>550", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )

    fake_snap = Snapshot.objects.create(profile=p, includes=["quotes"])
    with patch("apps.triggers.tasks.capture", return_value=fake_snap) as cap, \
         patch("apps.triggers.tasks.serialize_for_ai", return_value="payload"), \
         patch("apps.triggers.tasks.run_ai_on_message") as ai, \
         patch("apps.triggers.tasks.notify") as notify:
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 551.0})

    cap.assert_called_once()
    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.snapshot_id == fake_snap.id
    assert firing.thread is not None
    assert firing.cost_capped is False
    ai.delay.assert_called_once()
    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["kind"] == "trigger"
    assert kwargs["title"] == "SPY>550"
    assert kwargs["link"] == f"/threads/{firing.thread_id}"
    t.refresh_from_db()
    assert t.last_fired_at is not None


@pytest.mark.django_db
def test_fire_trigger_cost_capped_skips_ai(fake_redis, provider_cfg):
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    fake_snap = Snapshot.objects.create(profile=p, includes=["quotes"])

    def cap_exceeded(*a, **kw):
        raise CostCapExceededError("over cap")

    with patch("apps.triggers.tasks.capture", return_value=fake_snap), \
         patch("apps.triggers.tasks.check_daily_cap", side_effect=cap_exceeded), \
         patch("apps.triggers.tasks.run_ai_on_message") as ai, \
         patch("apps.triggers.tasks.notify") as notify:
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 100.0})

    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.cost_capped is True
    assert firing.thread is None
    ai.delay.assert_not_called()
    assert notify.call_args.kwargs["kind"] == "cost_limit"


@pytest.mark.django_db
def test_fire_trigger_capture_failure_notifies_error(fake_redis, provider_cfg):
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )

    with patch("apps.triggers.tasks.capture", side_effect=RuntimeError("schwab 503")), \
         patch("apps.triggers.tasks.run_ai_on_message") as ai, \
         patch("apps.triggers.tasks.notify") as notify:
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 100.0})

    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.snapshot is None
    assert firing.thread is None
    ai.delay.assert_not_called()
    assert notify.call_args.kwargs["kind"] == "error"


@pytest.mark.django_db
def test_fire_trigger_idempotent_via_redis_lock(fake_redis, provider_cfg):
    """Second concurrent invocation should no-op while the first holds the lock."""
    from apps.triggers.tasks import fire_trigger
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    # Seed lock → second call should return without creating a firing
    fake_redis.set(f"trigger:fire:{t.id}", "1", ex=60)

    fake_snap = Snapshot.objects.create(profile=p, includes=[])
    with patch("apps.triggers.tasks.capture", return_value=fake_snap), \
         patch("apps.triggers.tasks.run_ai_on_message"), \
         patch("apps.triggers.tasks.notify"):
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 100.0})

    assert TriggerFiring.objects.filter(trigger=t).count() == 0
