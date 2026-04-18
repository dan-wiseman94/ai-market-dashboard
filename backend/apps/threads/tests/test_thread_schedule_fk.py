import pytest

from apps.observer.models import ObserverSchedule
from apps.profiles.models import TradingProfile
from apps.threads.models import Thread


@pytest.mark.django_db
def test_thread_can_attach_to_an_observer_schedule():
    p = TradingProfile.objects.create(name="P", style="x")
    s = ObserverSchedule.objects.create(name="hourly", profile=p)
    t = Thread.objects.create(kind="observer", profile=p, schedule=s, title="Observer: P")
    assert t.schedule_id == s.id
    assert s.threads.filter(id=t.id).exists()


@pytest.mark.django_db
def test_thread_schedule_fk_is_nullable_for_v1_per_profile_thread():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="observer", profile=p, title="Observer: P")
    assert t.schedule is None
