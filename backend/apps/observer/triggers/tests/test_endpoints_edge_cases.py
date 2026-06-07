"""Error and fallback branches of the trigger endpoints: evaluate-by-id,
missing condition, malformed pagination params, and backtest validation."""

from unittest.mock import patch

import fakeredis
import pytest
from rest_framework.test import APIClient

from apps.observer.models import EventTrigger
from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="P", style="x")


@pytest.mark.django_db
def test_evaluate_by_trigger_id_uses_stored_condition(fake_redis, api, profile):
    t = EventTrigger.objects.create(
        name="r",
        profile=profile,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 551.0}}
    ):
        resp = api.post("/api/triggers/evaluate/", {"trigger_id": t.id}, format="json")
    assert resp.status_code == 200
    assert resp.json()["matched"] is True


@pytest.mark.django_db
def test_evaluate_by_unknown_trigger_id_404(api):
    resp = api.post("/api/triggers/evaluate/", {"trigger_id": 999999}, format="json")
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


@pytest.mark.django_db
def test_evaluate_without_condition_or_id_400(api):
    resp = api.post("/api/triggers/evaluate/", {}, format="json")
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_condition"


@pytest.mark.django_db
def test_firings_pagination_falls_back_on_garbage_params(api, profile):
    t = EventTrigger.objects.create(
        name="r",
        profile=profile,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 1},
    )
    resp = api.get(f"/api/triggers/{t.id}/firings/?page=abc&size=xyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["size"] == 20


@pytest.mark.django_db
def test_backtest_rejects_invalid_condition(api):
    resp = api.post(
        "/api/triggers/backtest/",
        {
            "condition": {"metric": "nope", "op": ">", "value": 1},
            "start": "2026-01-01",
            "end": "2026-02-01",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_condition"


@pytest.mark.django_db
def test_backtest_missing_condition_400(api):
    resp = api.post(
        "/api/triggers/backtest/", {"start": "2026-01-01", "end": "2026-02-01"}, format="json"
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_condition"


@pytest.mark.django_db
def test_firings_recent_limit_falls_back_on_garbage_param(api):
    resp = api.get("/api/triggers/firings/recent/?limit=abc")
    assert resp.status_code == 200
    assert resp.json() == []
