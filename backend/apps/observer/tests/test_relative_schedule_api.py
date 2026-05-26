import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_create_relative_schedule_without_cron():
    profile = TradingProfile.objects.create(name="p", style="s")
    c = APIClient()
    r = c.post(
        "/api/observer/schedules/",
        {
            "name": "eod",
            "profile": profile.id,
            "fire_mode": "relative_to_close",
            "close_offset_minutes": 5,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    assert r.json()["fire_mode"] == "relative_to_close"
    # no PeriodicTask for relative mode
    from apps.observer.models import ObserverSchedule

    assert ObserverSchedule.objects.get(id=r.json()["id"]).periodic_task is None


@pytest.mark.django_db
def test_cron_schedule_still_requires_cron():
    profile = TradingProfile.objects.create(name="p", style="s")
    c = APIClient()
    r = c.post(
        "/api/observer/schedules/",
        {
            "name": "x",
            "profile": profile.id,
            "fire_mode": "cron",
        },
        format="json",
    )
    assert r.status_code == 400
