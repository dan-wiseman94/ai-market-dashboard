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
    # The view get_or_create()s the thread for an existing profile, so 200 is the
    # only reachable outcome — accepting 404 here would hide the thread going missing.
    assert r.status_code == 200
    body = r.json()
    assert body["profile_id"] == pid
    assert body["kind"] == "observer"
    assert isinstance(body["messages"], list)


@pytest.mark.integration
def test_observer_thread_view_404s_for_an_unknown_profile(api_client) -> None:
    assert api_client.get("/api/observer/threads/99999999/").status_code == 404


@pytest.mark.integration
def test_market_status_endpoint(api_client) -> None:
    r = api_client.get("/api/observer/market-status/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["is_open"], bool)
    # Both are ISO timestamps, or null when the calendar has no next session.
    for key in ("next_open", "next_close"):
        assert body[key] is None or isinstance(body[key], str)
