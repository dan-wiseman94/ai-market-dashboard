"""Error and fallback branches of the trigger endpoints: evaluate-by-id,
missing condition, malformed pagination params, and backtest validation."""

from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.models import EventTrigger, TriggerFiring


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


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
def test_firings_pagination_falls_back_on_garbage_page_size(api, profile):
    t = EventTrigger.objects.create(
        name="r",
        profile=profile,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 1},
    )
    TriggerFiring.objects.create(trigger=t, matched_values={})
    # DRF PageNumberPagination: a garbage page_size silently falls back to the default.
    resp = api.get(f"/api/triggers/{t.id}/firings/?page_size=xyz")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 1


@pytest.mark.django_db
def test_firings_pagination_garbage_page_is_404(api, profile):
    t = EventTrigger.objects.create(
        name="r",
        profile=profile,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 1},
    )
    TriggerFiring.objects.create(trigger=t, matched_values={})
    # DRF PageNumberPagination: an invalid page is NotFound, not clamped.
    resp = api.get(f"/api/triggers/{t.id}/firings/?page=abc")
    assert resp.status_code == 404


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
