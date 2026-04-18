from unittest.mock import patch

import pytest
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APIClient

from apps.observer.models import ObserverSchedule
from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="P", style="x")


@pytest.mark.django_db
def test_create_schedule_with_valid_cron(api, profile):
    resp = api.post("/api/observer/schedules/", {
        "name": "hourly", "profile": profile.id, "cron": "0 * * * *",
    }, format="json")
    assert resp.status_code == 201, resp.content
    sid = resp.json()["id"]
    s = ObserverSchedule.objects.get(id=sid)
    assert s.periodic_task is not None
    assert s.periodic_task.crontab.minute == "0"
    assert PeriodicTask.objects.filter(task="observer.run_observer").count() == 1


@pytest.mark.django_db
def test_create_schedule_invalid_cron_returns_400(api, profile):
    resp = api.post("/api/observer/schedules/", {
        "name": "bad", "profile": profile.id, "cron": "bogus",
    }, format="json")
    assert resp.status_code == 400
    body = resp.json()
    assert "cron" in body


@pytest.mark.django_db
def test_patch_enabled_flips_periodic_task(api, profile):
    resp = api.post("/api/observer/schedules/", {
        "name": "x", "profile": profile.id, "cron": "0 * * * *",
    }, format="json")
    sid = resp.json()["id"]
    resp2 = api.patch(f"/api/observer/schedules/{sid}/", {"enabled": False}, format="json")
    assert resp2.status_code == 200
    s = ObserverSchedule.objects.get(id=sid)
    assert s.enabled is False
    assert s.periodic_task.enabled is False


@pytest.mark.django_db
def test_delete_schedule_drops_periodic_task(api, profile):
    resp = api.post("/api/observer/schedules/", {
        "name": "x", "profile": profile.id, "cron": "0 * * * *",
    }, format="json")
    sid = resp.json()["id"]
    resp2 = api.delete(f"/api/observer/schedules/{sid}/")
    assert resp2.status_code == 204
    assert ObserverSchedule.objects.count() == 0
    assert PeriodicTask.objects.filter(task="observer.run_observer").count() == 0


@pytest.mark.django_db
def test_run_now_calls_run_observer(api, profile):
    resp = api.post("/api/observer/schedules/", {
        "name": "x", "profile": profile.id, "cron": "0 * * * *",
    }, format="json")
    sid = resp.json()["id"]
    with patch("apps.observer.views.run_observer_task") as fake:
        resp2 = api.post(f"/api/observer/schedules/{sid}/run-now/")
    assert resp2.status_code == 202
    fake.delay.assert_called_once_with(schedule_id=sid)
