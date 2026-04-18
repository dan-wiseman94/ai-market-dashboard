from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

from apps.export.models import ExportJob


@pytest.mark.django_db
def test_create_enqueues(client: Client) -> None:
    with patch("apps.export.views.build_export") as task:
        resp = client.post(
            "/api/export/",
            data={"scope": {"threads": "all"}},
            content_type="application/json",
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    task.delay.assert_called_once()
    assert ExportJob.objects.count() == 1


@pytest.mark.django_db
def test_list(client: Client) -> None:
    ExportJob.objects.create(scope={}, format="zip", status="done", filename="x.zip", size_bytes=1, sha256="a" * 64)
    resp = client.get("/api/export/")
    assert resp.status_code == 200
    body = resp.json()
    rows = body.get("results", body)
    assert len(rows) == 1


@pytest.mark.django_db
def test_download_409_before_done(client: Client) -> None:
    job = ExportJob.objects.create(scope={}, format="zip", status="running")
    resp = client.get(f"/api/export/{job.id}/download/")
    assert resp.status_code == 409


@pytest.mark.django_db
def test_download_when_done(client: Client, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    f = tmp_path / "done.zip"
    f.write_bytes(b"zipcontent" * 10)
    job = ExportJob.objects.create(
        scope={}, format="zip", status="done", filename=f.name,
        size_bytes=f.stat().st_size, sha256="z" * 64,
    )
    resp = client.get(f"/api/export/{job.id}/download/")
    assert resp.status_code == 200
    assert "attachment" in resp["Content-Disposition"]


@pytest.mark.django_db
def test_delete_unlinks_file(client: Client, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    f = tmp_path / "del.zip"
    f.write_bytes(b"x")
    job = ExportJob.objects.create(
        scope={}, format="zip", status="done", filename=f.name, size_bytes=1, sha256="x" * 64,
    )
    resp = client.delete(f"/api/export/{job.id}/")
    assert resp.status_code == 204
    job.refresh_from_db()
    assert job.status == "deleted"
    assert not f.exists()


@pytest.mark.django_db
def test_single_thread_endpoint(client: Client) -> None:
    from apps.threads.models import Thread
    t = Thread.objects.create(kind="chat", title="T")
    with patch("apps.export.views.build_export"):
        resp = client.post(f"/api/export/thread/{t.id}/")
    assert resp.status_code == 202
    job = ExportJob.objects.get()
    assert job.scope == {"threads": [t.id]}
