from unittest.mock import patch

import pytest
from django_celery_beat.models import PeriodicTask

from apps.observer.models import ObserverSchedule
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_create_schedule_with_valid_cron(api, profile):
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "hourly",
            "profile": profile.id,
            "cron": "0 * * * *",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    sid = resp.json()["id"]
    s = ObserverSchedule.objects.get(id=sid)
    assert s.periodic_task is not None
    assert s.periodic_task.crontab.minute == "0"
    assert PeriodicTask.objects.filter(task="observer.run_observer").count() == 1


@pytest.mark.django_db
def test_create_schedule_invalid_cron_returns_400(api, profile):
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "bad",
            "profile": profile.id,
            "cron": "bogus",
        },
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "cron" in body


@pytest.mark.django_db
def test_patch_enabled_flips_periodic_task(api, profile):
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "x",
            "profile": profile.id,
            "cron": "0 * * * *",
        },
        format="json",
    )
    sid = resp.json()["id"]
    resp2 = api.patch(f"/api/observer/schedules/{sid}/", {"enabled": False}, format="json")
    assert resp2.status_code == 200
    s = ObserverSchedule.objects.get(id=sid)
    assert s.enabled is False
    assert s.periodic_task is not None
    assert s.periodic_task.enabled is False


@pytest.mark.django_db
def test_delete_schedule_drops_periodic_task(api, profile):
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "x",
            "profile": profile.id,
            "cron": "0 * * * *",
        },
        format="json",
    )
    sid = resp.json()["id"]
    resp2 = api.delete(f"/api/observer/schedules/{sid}/")
    assert resp2.status_code == 204
    assert ObserverSchedule.objects.count() == 0
    assert PeriodicTask.objects.filter(task="observer.run_observer").count() == 0


@pytest.mark.django_db
def test_consensus_mode_is_settable_via_api(api, profile):
    # consensus is a fully-wired backend mode (run.py feeds it through
    # _run_consensus_and_record). It must be reachable via the API + round-trip
    # in the response, so it can be enabled without direct DB editing.
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "c",
            "profile": profile.id,
            "cron": "0 * * * *",
            "structured": True,
            "consensus": True,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["consensus"] is True
    assert ObserverSchedule.objects.get(id=resp.json()["id"]).consensus is True


@pytest.mark.django_db
def test_run_now_calls_fire_observer(api, profile):
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "x",
            "profile": profile.id,
            "cron": "0 * * * *",
        },
        format="json",
    )
    sid = resp.json()["id"]
    with patch("apps.observer.views.fire_observer_task") as fake:
        resp2 = api.post(f"/api/observer/schedules/{sid}/run-now/")
    assert resp2.status_code == 202
    fake.delay.assert_called_once_with(schedule_id=sid)


@pytest.mark.django_db
def test_create_structured_schedule_requires_claude_provider(api):
    """structured runs through Anthropic messages.parse — a schedule resolving
    to a non-Claude provider must be rejected at configuration time, not fail
    every fire with an opaque 401."""
    p = TradingProfile.objects.create(name="O", style="x", default_provider="openai")
    resp = api.post(
        "/api/observer/schedules/",
        {"name": "s", "profile": p.id, "cron": "0 * * * *", "structured": True},
        format="json",
    )
    assert resp.status_code == 400
    assert "structured" in resp.json()


@pytest.mark.django_db
def test_create_batch_schedule_requires_claude_provider(api, profile):
    resp = api.post(
        "/api/observer/schedules/",
        {
            "name": "s",
            "profile": profile.id,
            "cron": "0 * * * *",
            "use_batch": True,
            "override_provider": "local",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "use_batch" in resp.json()


@pytest.mark.django_db
def test_create_structured_schedule_with_claude_provider_ok(api, profile):
    # profile.default_provider defaults to "claude"
    resp = api.post(
        "/api/observer/schedules/",
        {"name": "s", "profile": profile.id, "cron": "0 * * * *", "structured": True},
        format="json",
    )
    assert resp.status_code == 201, resp.content


@pytest.mark.django_db
def test_patch_use_batch_on_non_claude_schedule_rejected(api):
    p = TradingProfile.objects.create(name="O2", style="x", default_provider="openai")
    resp = api.post(
        "/api/observer/schedules/",
        {"name": "s", "profile": p.id, "cron": "0 * * * *"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    sid = resp.json()["id"]
    resp = api.patch(f"/api/observer/schedules/{sid}/", {"use_batch": True}, format="json")
    assert resp.status_code == 400
    assert "use_batch" in resp.json()
