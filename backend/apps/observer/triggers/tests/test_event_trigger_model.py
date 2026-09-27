import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.observer.models import EventTrigger
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_event_trigger_unique_name_per_profile():
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(name="rule", profile=p, condition={"all": []})
    with pytest.raises(IntegrityError):
        EventTrigger.objects.create(name="rule", profile=p, condition={"all": []})


@pytest.mark.django_db
def test_event_trigger_clean_runs_dsl_validator():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger(name="bad", profile=p, condition={"metric": "nope"})
    with pytest.raises(ValidationError):
        t.full_clean()
