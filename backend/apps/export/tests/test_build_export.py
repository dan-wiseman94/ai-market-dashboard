# backend/apps/export/tests/test_build_export.py
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from apps.export.models import ExportJob
from apps.export.tasks import build_export
from apps.threads.models import Message, Thread


@pytest.mark.django_db
def test_build_export_writes_expected_structure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))

    t = Thread.objects.create(kind="chat", title="Alpha")
    Message.objects.create(thread=t, role="user", content={"text": "hi"}, status="done")

    job = ExportJob.objects.create(
        scope={
            "threads": "all",
            "snapshots": "all",
            "observations": True,
            "triggers": True,
            "profiles": True,
            "watchlists": True,
        },
        format="zip",
        status="pending",
    )
    build_export(job.id)

    job.refresh_from_db()
    assert job.status == "done"
    assert job.filename
    assert job.size_bytes > 0
    assert len(job.sha256) == 64

    path = tmp_path / job.filename
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert any("manifest.json" in n for n in names)
        assert any(f"threads/{t.id}/meta.json" in n for n in names)
        assert any(f"threads/{t.id}/thread.md" in n for n in names)

        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name).decode())
        assert manifest["version"] == 1
        assert manifest["counts"]["threads"] == 1


@pytest.mark.django_db
def test_build_export_failure_records_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    job = ExportJob.objects.create(scope={}, format="zip", status="pending")

    from unittest.mock import patch
    with patch("apps.export.services.zipfile.ZipFile", side_effect=RuntimeError("disk full")):
        build_export(job.id)

    job.refresh_from_db()
    assert job.status == "failed"
    assert "disk full" in job.error
