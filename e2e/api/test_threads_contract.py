"""Threads endpoints — list + create + per-thread retrieval contract."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_thread_list(api_client, threads) -> None:
    r = api_client.get("/api/threads/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)


@pytest.mark.integration
def test_thread_detail_shape(api_client, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.filter(title="E2E plain thread").first()
    assert t is not None
    r = api_client.get(f"/api/threads/{t.id}/")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == t.id
    assert body["title"] == "E2E plain thread"
