import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger


@pytest.mark.django_db
def test_event_trigger_defaults():
    p = TradingProfile.objects.create(name="Default", style="x")
    t = EventTrigger.objects.create(
        name="SPY > 550",
        profile=p,
        condition={"all": [{"metric": "price", "ticker": "SPY", "op": ">", "value": 550}]},
    )
    assert t.enabled is True
    assert t.cooldown_seconds == 1800
    assert t.last_fired_at is None


@pytest.mark.django_db
def test_event_trigger_unique_name_per_profile():
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(name="rule", profile=p, condition={"all": []})
    with pytest.raises(IntegrityError):
        EventTrigger.objects.create(name="rule", profile=p, condition={"all": []})


@pytest.mark.django_db
def test_event_trigger_same_name_different_profile_ok():
    p1 = TradingProfile.objects.create(name="P1", style="x")
    p2 = TradingProfile.objects.create(name="P2", style="x")
    EventTrigger.objects.create(name="rule", profile=p1, condition={"all": []})
    EventTrigger.objects.create(name="rule", profile=p2, condition={"all": []})


@pytest.mark.django_db
def test_event_trigger_clean_runs_dsl_validator():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger(name="bad", profile=p, condition={"metric": "nope"})
    with pytest.raises(ValidationError):
        t.full_clean()
