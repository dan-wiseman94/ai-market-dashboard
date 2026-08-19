import pytest

from apps.observer.models import EventTrigger, TriggerFiring
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_firings_list_for_trigger(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={"price:SPY": 551.0})
    TriggerFiring.objects.create(trigger=t, matched_values={"price:SPY": 552.0})
    resp = api.get(f"/api/triggers/{t.id}/firings/")
    assert resp.status_code == 200
    body = resp.json()
    # DRF PageNumberPagination envelope
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    assert body["next"] is None
    assert body["previous"] is None
    assert len(body["results"]) == 2
    # Newest first
    assert body["results"][0]["matched_values"] == {"price:SPY": 552.0}


@pytest.mark.django_db
def test_firings_page_size_and_page_params(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    for i in range(5):
        TriggerFiring.objects.create(trigger=t, matched_values={"price:SPY": 550.0 + i})

    resp = api.get(f"/api/triggers/{t.id}/firings/?page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 5
    assert len(body["results"]) == 2
    assert body["next"] is not None
    assert body["previous"] is None
    first_page_ids = [row["id"] for row in body["results"]]

    resp2 = api.get(f"/api/triggers/{t.id}/firings/?page_size=2&page=2")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["results"]) == 2
    assert body2["previous"] is not None
    assert [row["id"] for row in body2["results"]] != first_page_ids


@pytest.mark.django_db
def test_firings_page_size_capped_at_50(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    for _ in range(55):
        TriggerFiring.objects.create(trigger=t, matched_values={})

    resp = api.get(f"/api/triggers/{t.id}/firings/?page_size=9999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 55
    assert len(body["results"]) == 50


@pytest.mark.django_db
def test_firings_recent_global(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t1 = EventTrigger.objects.create(name="r1", profile=p, condition={"all": []})
    t2 = EventTrigger.objects.create(name="r2", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t1, matched_values={"vix": 25.0})
    TriggerFiring.objects.create(trigger=t2, matched_values={"price:SPY": 550.0})

    resp = api.get("/api/triggers/firings/recent/?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = {row["trigger_name"] for row in body}
    assert names == {"r1", "r2"}


@pytest.mark.django_db
def test_firings_recent_respects_limit(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    for _ in range(7):
        TriggerFiring.objects.create(trigger=t, matched_values={})

    resp = api.get("/api/triggers/firings/recent/?limit=3")
    body = resp.json()
    assert len(body) == 3
