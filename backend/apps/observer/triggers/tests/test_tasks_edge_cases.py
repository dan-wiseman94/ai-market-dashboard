"""Failure/edge branches of the trigger Celery tasks: a trigger whose condition
blows up the evaluator is auto-disabled, firing with no ProviderConfig still runs
the AI (no cap to enforce), and the _redis() constructor."""

from unittest.mock import patch

import fakeredis
import pytest
import redis as redis_lib

from apps.observer.models import EventTrigger, TriggerFiring
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.tasks._redis", return_value=client):
        yield client


def test_redis_factory_builds_a_client_without_connecting():
    from apps.observer.triggers.tasks import _redis

    assert isinstance(_redis(), redis_lib.Redis)


@pytest.mark.django_db
def test_evaluator_exception_disables_the_trigger():
    from apps.observer.triggers.tasks import evaluate_triggers

    p = TradingProfile.objects.create(name="P", style="x")
    # BTC-USD is a 24/7 (crypto) market, so the trigger always passes the live filter.
    t = EventTrigger.objects.create(
        name="bad",
        profile=p,
        condition={"metric": "price", "ticker": "BTC-USD", "op": ">", "value": 1},
    )
    with (
        patch("apps.observer.triggers.tasks.metrics.build_snapshot", return_value={}),
        patch("apps.observer.triggers.tasks.cooldown_blocks", return_value=False),
        patch("apps.observer.triggers.tasks.evaluator.evaluate", side_effect=ValueError("bad leaf")),
    ):
        evaluate_triggers()

    t.refresh_from_db()
    assert t.enabled is False


@pytest.mark.django_db
def test_fire_without_provider_config_still_runs_ai(fake_redis):
    """No ProviderConfig => no cap to enforce; the fire proceeds to the AI run."""
    from apps.observer.triggers.tasks import fire_trigger

    # default_provider has no matching ProviderConfig row.
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    fake_snap = Snapshot.objects.create(profile=p, includes=["quotes"])
    with (
        patch("apps.observer.triggers.tasks.capture", return_value=fake_snap),
        patch("apps.observer.triggers.tasks.serialize_for_ai", return_value="payload"),
        patch("apps.observer.triggers.tasks.run_ai_on_message") as ai,
        patch("apps.observer.triggers.tasks.notify"),
    ):
        fire_trigger(trigger_id=t.id, matched_values={"price:SPY": 1.0})

    firing = TriggerFiring.objects.get(trigger=t)
    assert firing.cost_capped is False
    assert firing.thread is not None
    ai.delay.assert_called_once()
