from unittest.mock import patch

import fakeredis
import pytest
from freezegun import freeze_time

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger
from apps.triggers.tasks import evaluate_triggers


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with (
        patch("apps.triggers.metrics._redis", return_value=client),
        patch("apps.triggers.services.cooldown._redis", return_value=client),
    ):
        yield client


@pytest.mark.django_db
@freeze_time("2026-04-18 15:00:00")  # Saturday — market closed
def test_tick_noops_when_market_closed(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(
        name="r", profile=p, condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0}
    )
    with (
        patch("apps.triggers.metrics.fetch_quotes") as fq,
        patch("apps.triggers.tasks.fire_trigger") as fire,
    ):
        evaluate_triggers()
    fq.assert_not_called()
    fire.delay.assert_not_called()


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET — market open
def test_tick_enqueues_fire_when_matched(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with (
        patch("apps.triggers.metrics.fetch_quotes") as fq,
        patch("apps.triggers.tasks.fire_trigger") as fire,
    ):
        fq.return_value = {"SPY": {"last": 551.0}}
        evaluate_triggers()
    fire.delay.assert_called_once()
    args, kwargs = fire.delay.call_args
    assert kwargs.get("trigger_id", args[0] if args else None) == t.id


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")
def test_tick_skips_disabled_triggers(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(
        name="r",
        profile=p,
        enabled=False,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with (
        patch("apps.triggers.metrics.fetch_quotes") as fq,
        patch("apps.triggers.tasks.fire_trigger") as fire,
    ):
        evaluate_triggers()
    fq.assert_not_called()
    fire.delay.assert_not_called()


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")
def test_tick_marks_rearmed_when_condition_false(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
    )
    with (
        patch("apps.triggers.metrics.fetch_quotes") as fq,
        patch("apps.triggers.tasks.fire_trigger") as fire,
    ):
        fq.return_value = {"SPY": {"last": 551.0}}
        evaluate_triggers()
    fire.delay.assert_not_called()
    assert fake_redis.exists(f"trigger:armed:{t.id}") == 1


@pytest.mark.django_db
@freeze_time("2026-04-15 14:00:00")
def test_tick_skips_when_cooldown_active(fake_redis):
    from django.utils import timezone as dj_tz

    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(
        name="r",
        profile=p,
        cooldown_seconds=3600,
        last_fired_at=dj_tz.now(),
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with (
        patch("apps.triggers.metrics.fetch_quotes") as fq,
        patch("apps.triggers.tasks.fire_trigger") as fire,
    ):
        fq.return_value = {"SPY": {"last": 551.0}}
        evaluate_triggers()
    fire.delay.assert_not_called()
