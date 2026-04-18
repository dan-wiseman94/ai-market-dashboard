import pytest

from apps.observer.services.threads import get_or_create_observer_thread
from apps.profiles.models import TradingProfile
from apps.threads.models import Thread


@pytest.mark.django_db
def test_get_or_create_observer_thread_idempotent_per_profile():
    p = TradingProfile.objects.create(name="P", style="x")
    t1 = get_or_create_observer_thread(p)
    t2 = get_or_create_observer_thread(p)
    assert t1.id == t2.id
    assert Thread.objects.filter(profile=p, kind="observer").count() == 1
    assert t1.kind == "observer"
    assert t1.title == "Observer: P"
    assert t1.schedule is None


@pytest.mark.django_db
def test_get_or_create_observer_thread_separate_per_profile():
    a = TradingProfile.objects.create(name="A", style="x")
    b = TradingProfile.objects.create(name="B", style="x")
    ta = get_or_create_observer_thread(a)
    tb = get_or_create_observer_thread(b)
    assert ta.id != tb.id
