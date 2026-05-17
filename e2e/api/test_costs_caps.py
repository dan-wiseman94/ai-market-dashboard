"""Costs summary + caps endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_costs_today(api_client, analytics) -> None:
    r = api_client.get("/api/costs/today/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


@pytest.mark.integration
def test_costs_summary(api_client, analytics) -> None:
    r = api_client.get("/api/costs/summary")
    assert r.status_code == 200


@pytest.mark.integration
def test_costs_caps_get(api_client, minimal) -> None:
    """The endpoint returns either a dict keyed by provider OR a list of provider records."""
    r = api_client.get("/api/costs/caps")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, (dict, list))
    if isinstance(body, list):
        assert any(row.get("provider") in ("claude", "openai", "local") for row in body)
    else:
        assert any(k in body for k in ("claude", "openai", "local"))


@pytest.mark.integration
def test_costs_export_csv(api_client, analytics) -> None:
    r = api_client.get("/api/costs/export.csv")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "csv" in ct or "text" in ct
