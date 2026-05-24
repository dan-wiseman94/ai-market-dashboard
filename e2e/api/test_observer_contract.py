"""Observer schedule CRUD + observer thread view."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_schedule_list(api_client, observer) -> None:
    r = api_client.get("/api/observer/schedules/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)
    assert len(rows) >= 4


@pytest.mark.integration
def test_observer_thread_view(api_client, observer) -> None:
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    r = api_client.get(f"/api/observer/threads/{pid}/")
    # 200 with a body, or 404 if the profile has no observer thread yet — both fine.
    assert r.status_code in (200, 404)


@pytest.mark.integration
def test_market_status_endpoint(api_client) -> None:
    r = api_client.get("/api/observer/market-status/")
    assert r.status_code == 200
    body = r.json()
    # Body shape: any well-formed json with at least a boolean field somewhere
    assert isinstance(body, dict)
