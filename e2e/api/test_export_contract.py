"""Export list + per-thread endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_export_list(api_client, threads) -> None:
    r = api_client.get("/api/export/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)


@pytest.mark.integration
def test_single_thread_export(api_client, threads) -> None:
    """``/api/export/thread/<id>/`` may be GET or POST depending on M-version. Try both."""
    from apps.threads.models import Thread

    t = Thread.objects.filter(title="E2E plain thread").first()
    assert t is not None

    r = api_client.post(f"/api/export/thread/{t.id}/", json={})
    if r.status_code == 405:
        r = api_client.get(f"/api/export/thread/{t.id}/")
    assert r.status_code in (200, 202)
    ct = r.headers.get("content-type", "")
    assert any(c in ct for c in ("application/json", "application/zip", "application/octet-stream"))
