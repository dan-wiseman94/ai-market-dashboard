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


@pytest.mark.django_db
def test_get_or_create_observer_thread_tolerates_existing_duplicates():
    """get_or_create is not atomic (no unique constraint), so a race between a beat-fired
    observer run and another create can leave two schedule-less observer threads for a
    profile. The resolver must then return one deterministically (the oldest) rather than
    raise Thread.MultipleObjectsReturned (which would 500 every observer fire / timeline
    load). Surfaced by the e2e observer seed under random order."""
    p = TradingProfile.objects.create(name="P", style="x")
    t1 = Thread.objects.create(profile=p, kind="observer", schedule=None, title="Observer: P")
    Thread.objects.create(profile=p, kind="observer", schedule=None, title="Observer: P")
    got = get_or_create_observer_thread(p)
    assert got.id == t1.id  # oldest wins, deterministically; no crash
