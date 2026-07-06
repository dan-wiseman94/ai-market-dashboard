"""Failure/edge branches of the trigger Celery tasks: a trigger whose condition
blows up the evaluator is auto-disabled, firing with no ProviderConfig still runs
the AI (no cap to enforce), and the _redis() constructor."""

from unittest.mock import patch

import fakeredis
import pytest
import redis as redis_lib
from django.utils import timezone

from apps.observer.models import EventTrigger, Notification, TriggerFiring
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
        patch(
            "apps.observer.triggers.tasks.evaluator.evaluate", side_effect=ValueError("bad leaf")
        ),
    ):
        evaluate_triggers()

    t.refresh_from_db()
    assert t.enabled is False


@pytest.mark.django_db
def test_evaluator_exception_notifies_on_auto_disable():
    """Auto-disabling a standing alert must be visible in the notification bell —
    a silently-off trigger is the worst failure mode for an alerting feature."""
    from apps.observer.triggers.tasks import evaluate_triggers

    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(
        name="bad",
        profile=p,
        condition={"metric": "price", "ticker": "BTC-USD", "op": ">", "value": 1},
    )
    with (
        patch("apps.observer.triggers.tasks.metrics.build_snapshot", return_value={}),
        patch("apps.observer.triggers.tasks.cooldown_blocks", return_value=False),
        patch(
            "apps.observer.triggers.tasks.evaluator.evaluate", side_effect=ValueError("bad leaf")
        ),
    ):
        evaluate_triggers()

    n = Notification.objects.filter(kind="error").first()
    assert n is not None
    assert "disabled" in n.title.lower()


@pytest.mark.django_db
def test_redis_error_in_cooldown_skips_tick_without_disabling():
    """A transient Redis error inside cooldown_blocks is an infra hiccup, NOT a bad
    condition — the trigger is skipped for this tick, never auto-disabled."""
    from apps.observer.triggers.tasks import evaluate_triggers

    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="ok",
        profile=p,
        condition={"metric": "price", "ticker": "BTC-USD", "op": ">", "value": 1},
    )
    with (
        patch("apps.observer.triggers.tasks.metrics.build_snapshot", return_value={}),
        patch(
            "apps.observer.triggers.tasks.cooldown_blocks",
            side_effect=redis_lib.RedisError("connection reset"),
        ),
        patch("apps.observer.triggers.tasks.evaluator.evaluate") as evaluate,
        patch("apps.observer.triggers.tasks.fire_trigger") as fire,
    ):
        result = evaluate_triggers()

    evaluate.assert_not_called()
    fire.delay.assert_not_called()
    t.refresh_from_db()
    assert t.enabled is True  # NOT disabled on an infra hiccup
    assert result["fires"] == 0


@pytest.mark.django_db
def test_concurrent_tick_loses_cas_and_does_not_enqueue_duplicate_fire():
    """Two ticks racing on the same trigger both pass cooldown_blocks (each reads a
    stale in-memory last_fired_at). The compare-and-set on last_fired_at lets only
    one win the claim; the loser must NOT enqueue a second (double-billing) fire."""
    from apps.observer.triggers.tasks import evaluate_triggers

    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(
        name="ok",
        profile=p,
        condition={"metric": "price", "ticker": "BTC-USD", "op": ">", "value": 1},
    )

    def _competitor_wins(trigger_id):
        # Simulate another concurrent tick stamping last_fired_at between our read of
        # the trigger row and our CAS — the CAS's WHERE last_fired_at=<old> now misses.
        EventTrigger.objects.filter(id=trigger_id).update(last_fired_at=timezone.now())

    with (
        patch("apps.observer.triggers.tasks.metrics.build_snapshot", return_value={}),
        patch("apps.observer.triggers.tasks.cooldown_blocks", return_value=False),
        patch("apps.observer.triggers.tasks.evaluator.evaluate", return_value=(True, {"x": 1})),
        patch("apps.observer.triggers.tasks.mark_fired", side_effect=_competitor_wins),
        patch("apps.observer.triggers.tasks.fire_trigger") as fire,
    ):
        result = evaluate_triggers()

    fire.delay.assert_not_called()
    assert result["fires"] == 0


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
