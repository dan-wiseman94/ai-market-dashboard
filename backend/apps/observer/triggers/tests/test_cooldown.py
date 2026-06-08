from datetime import timedelta
from unittest.mock import patch

import fakeredis
import pytest
from django.utils import timezone

from apps.observer.models import EventTrigger
from apps.observer.triggers.services.cooldown import cooldown_blocks, mark_fired, mark_rearmed
from apps.profiles.models import TradingProfile


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.services.cooldown._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_never_fired_never_blocks(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []}, cooldown_seconds=60)
    assert cooldown_blocks(t) is False


@pytest.mark.django_db
def test_within_time_window_blocks(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []}, cooldown_seconds=60)
    t.last_fired_at = timezone.now() - timedelta(seconds=30)
    t.save()
    assert cooldown_blocks(t) is True


@pytest.mark.django_db
def test_time_elapsed_but_not_rearmed_blocks(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []}, cooldown_seconds=60)
    t.last_fired_at = timezone.now() - timedelta(seconds=120)
    t.save()
    # No re-arm key set → blocked
    assert cooldown_blocks(t) is True


@pytest.mark.django_db
def test_time_elapsed_and_rearmed_passes(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []}, cooldown_seconds=60)
    t.last_fired_at = timezone.now() - timedelta(seconds=120)
    t.save()
    mark_rearmed(t.id)
    assert cooldown_blocks(t) is False


@pytest.mark.django_db
def test_mark_fired_clears_rearmed_flag(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    mark_rearmed(t.id)
    assert fake_redis.exists(f"trigger:armed:{t.id}") == 1
    mark_fired(t.id)
    assert fake_redis.exists(f"trigger:armed:{t.id}") == 0
