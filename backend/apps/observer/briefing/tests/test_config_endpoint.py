import pytest


@pytest.mark.django_db
def test_get_config_returns_singleton(api):
    r = api.get("/api/briefings/config/")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert "send_at_local" in r.json()


@pytest.mark.django_db
def test_patch_config_updates(api):
    r = api.patch(
        "/api/briefings/config/", {"enabled": False, "events_within_days": 14}, format="json"
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["events_within_days"] == 14
