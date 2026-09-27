import pytest

from apps.observer.models import EventTrigger
from apps.profiles.models import TradingProfile


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
