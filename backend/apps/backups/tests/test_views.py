from __future__ import annotations

import pytest
from django.test import Client

from apps.backups.models import BackupRecord


@pytest.fixture
def seeded(db, tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    f = tmp_path / "2026-04-18-023000.sql.gz"
    f.write_bytes(b"hello world" * 10)
    return BackupRecord.objects.create(
        filename=f.name,
        size_bytes=f.stat().st_size,
        sha256="s" * 64,
        kind="scheduled",
        status="ok",
    )


def test_list(client: Client, seeded) -> None:
    resp = client.get("/api/backups/")
    assert resp.status_code == 200
    data = resp.json()
    # DRF PageNumberPagination envelope
    assert set(data) == {"count", "next", "previous", "results"}
    assert data["count"] == 1
    assert data["results"][0]["filename"] == seeded.filename


def test_list_respects_page_size(client: Client, seeded, tmp_path) -> None:
    for i in range(2):
        f = tmp_path / f"2026-04-19-02300{i}.sql.gz"
        f.write_bytes(b"x")
        BackupRecord.objects.create(
            filename=f.name,
            size_bytes=1,
            sha256="s" * 64,
            kind="scheduled",
            status="ok",
        )
    resp = client.get("/api/backups/?page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert len(data["results"]) == 2
    assert data["next"] is not None


def test_run_now(client: Client, db) -> None:
    from unittest.mock import patch

    with patch("apps.backups.views.run_backup") as task:
        resp = client.post("/api/backups/run/")
        assert resp.status_code in (200, 202)
        task.delay.assert_called_once()


def test_download(client: Client, seeded) -> None:
    resp = client.get(f"/api/backups/{seeded.id}/download/")
    assert resp.status_code == 200
    body = b"".join(resp.streaming_content) if hasattr(resp, "streaming_content") else resp.content
    assert len(body) > 0
    assert "attachment" in resp["Content-Disposition"]


def test_delete(client: Client, seeded, tmp_path) -> None:
    resp = client.delete(f"/api/backups/{seeded.id}/")
    assert resp.status_code in (200, 204)
    seeded.refresh_from_db()
    assert seeded.status == "deleted"
    assert not (tmp_path / seeded.filename).exists()
