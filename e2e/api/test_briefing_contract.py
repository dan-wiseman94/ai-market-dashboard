"""Briefing API contract — /api/briefings/."""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.api
def test_briefing_config_get(api_client, minimal) -> None:
    r = api_client.get("/api/briefings/config/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"enabled", "send_at_local", "news_lookback_hours", "events_within_days"} <= set(body)


@pytest.mark.integration
@pytest.mark.api
def test_briefing_run_now_creates_run(api_client, minimal) -> None:
    r = api_client.post("/api/briefings/run/")
    assert r.status_code == 201, r.text
    body = r.json()
    assert {"id", "status", "data"} <= set(body)
    from apps.briefing.models import BriefingRun

    assert BriefingRun.objects.filter(id=body["id"]).exists()


@pytest.mark.integration
@pytest.mark.api
def test_briefing_latest_returns_a_run_after_run_now(api_client, minimal) -> None:
    api_client.post("/api/briefings/run/")
    r = api_client.get("/api/briefings/latest/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body and "status" in body
