import pytest

from apps.observer.models import BriefingConfig


@pytest.mark.django_db
def test_get_config_returns_singleton(api):
    r = api.get("/api/briefings/config/")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert "send_at_local" in r.json()


@pytest.mark.django_db
def test_get_config_exposes_the_spend_switches(api):
    """enabled and synthesis_enabled are both on out of the box and both must be
    visible: the scheduled briefing pays for an AI synthesis with no user action,
    so the UI needs a switch it can render."""
    body = api.get("/api/briefings/config/").json()
    assert body["enabled"] is True
    assert body["synthesis_enabled"] is True
    assert set(body) == {
        "enabled",
        "synthesis_enabled",
        "send_at_local",
        "profile",
        "news_lookback_hours",
        "events_within_days",
        "updated_at",
    }


@pytest.mark.django_db
def test_patch_config_toggles_synthesis(api):
    r = api.patch("/api/briefings/config/", {"synthesis_enabled": False}, format="json")
    assert r.status_code == 200
    assert r.json()["synthesis_enabled"] is False
    assert BriefingConfig.load().synthesis_enabled is False


@pytest.mark.django_db
def test_patch_config_updates(api):
    r = api.patch(
        "/api/briefings/config/", {"enabled": False, "events_within_days": 14}, format="json"
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["events_within_days"] == 14
