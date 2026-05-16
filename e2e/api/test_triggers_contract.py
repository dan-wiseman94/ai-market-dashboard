"""Triggers CRUD."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_trigger_list(api_client, triggers) -> None:
    r = api_client.get("/api/triggers/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)
    assert len(rows) >= 3


@pytest.mark.integration
def test_trigger_detail(api_client, triggers) -> None:
    from apps.triggers.models import EventTrigger

    t = EventTrigger.objects.get(name="E2E always fires")
    r = api_client.get(f"/api/triggers/{t.id}/")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "E2E always fires"
    assert body["enabled"] is True
    assert isinstance(body["condition"], dict)
