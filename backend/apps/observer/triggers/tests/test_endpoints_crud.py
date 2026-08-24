import pytest

from apps.observer.models import EventTrigger
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_list_triggers(api):
    p = TradingProfile.objects.create(name="P", style="x")
    EventTrigger.objects.create(name="r1", profile=p, condition={"all": []})
    EventTrigger.objects.create(name="r2", profile=p, condition={"any": []})
    resp = api.get("/api/triggers/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all("firings_count" in row for row in body)


@pytest.mark.django_db
def test_create_trigger_validates_dsl(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.post(
        "/api/triggers/",
        {
            "name": "bad",
            "profile": p.id,
            "condition": {"metric": "nope", "op": ">", "value": 1},
            "cooldown_seconds": 300,
            "enabled": True,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "condition" in resp.json()


@pytest.mark.django_db
def test_create_trigger_ok(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.post(
        "/api/triggers/",
        {
            "name": "SPY",
            "profile": p.id,
            "condition": {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
            "cooldown_seconds": 1800,
            "enabled": True,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert EventTrigger.objects.filter(name="SPY").exists()


@pytest.mark.django_db
def test_patch_toggle_enabled(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    resp = api.patch(f"/api/triggers/{t.id}/", {"enabled": False}, format="json")
    assert resp.status_code == 200
    t.refresh_from_db()
    assert t.enabled is False


@pytest.mark.django_db
def test_delete_cascades_firings(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    from apps.observer.models import TriggerFiring

    TriggerFiring.objects.create(trigger=t, matched_values={})
    resp = api.delete(f"/api/triggers/{t.id}/")
    assert resp.status_code == 204
    assert TriggerFiring.objects.count() == 0
