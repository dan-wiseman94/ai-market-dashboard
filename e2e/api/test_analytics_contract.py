"""Analytics — one test per card."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_leaderboard(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/leaderboard/?forward_hours=24")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("rows", [])
    assert isinstance(rows, list)
    for row in rows:
        assert "provider" in row
        assert "model" in row
        assert "coverage_pct" in row


@pytest.mark.integration
def test_cost_per_insight(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/cost-per-insight/")
    assert r.status_code == 200
    body = r.json()
    for key in ("insights", "trigger_fires", "total_cost_usd"):
        assert key in body


@pytest.mark.integration
def test_trigger_heatmap(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/trigger-heatmap/")
    assert r.status_code == 200
    body = r.json()
    cells = body.get("cells") if isinstance(body, dict) else body
    assert isinstance(cells, list)


@pytest.mark.integration
def test_observer_timeline(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/observer-timeline/")
    assert r.status_code == 200
    body = r.json()
    rows = body.get("rows") if isinstance(body, dict) else body
    assert isinstance(rows, list)


@pytest.mark.integration
def test_unusual_options(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/unusual-options/?ticker=AAPL")
    assert r.status_code == 200
    body = r.json()
    lines = body.get("lines") if isinstance(body, dict) else body
    assert isinstance(lines, list)
