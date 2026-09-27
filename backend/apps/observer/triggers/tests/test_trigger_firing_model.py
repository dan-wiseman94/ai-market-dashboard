import pytest

from apps.observer.models import EventTrigger, TriggerFiring
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_trigger_firing_deleted_on_trigger_cascade():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={})
    t.delete()
    assert TriggerFiring.objects.count() == 0
