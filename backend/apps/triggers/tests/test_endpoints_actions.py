from unittest.mock import patch

import fakeredis
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_fire_now_enqueues_fire_trigger(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with patch("apps.triggers.views.fire_trigger") as ft:
        ft.delay.return_value.id = "task-123"
        resp = api.post(f"/api/triggers/{t.id}/fire/")
    assert resp.status_code == 202
    ft.delay.assert_called_once()
    kwargs = ft.delay.call_args.kwargs
    assert kwargs["trigger_id"] == t.id


@pytest.mark.django_db
def test_fire_now_rejects_disabled(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r", profile=p, enabled=False,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    with patch("apps.triggers.views.fire_trigger") as ft:
        resp = api.post(f"/api/triggers/{t.id}/fire/")
    assert resp.status_code == 400
    ft.delay.assert_not_called()


@pytest.mark.django_db
def test_evaluate_with_condition_body(fake_redis, api):
    p = TradingProfile.objects.create(name="P", style="x")
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        resp = api.post("/api/triggers/evaluate/", {
            "profile": p.id,
            "condition": {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        }, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is True
    assert body["values"]["price:SPY"] == 551.0
    assert body["missing"] == []


@pytest.mark.django_db
def test_evaluate_rejects_invalid_dsl(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.post("/api/triggers/evaluate/", {
        "profile": p.id, "condition": {"metric": "nope", "op": ">", "value": 1},
    }, format="json")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_evaluate_reports_missing_metric_keys(fake_redis, api):
    p = TradingProfile.objects.create(name="P", style="x")
    with patch("apps.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {}  # Schwab returned nothing
        resp = api.post("/api/triggers/evaluate/", {
            "profile": p.id,
            "condition": {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        }, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is False
    assert "price:SPY" in body["missing"]
