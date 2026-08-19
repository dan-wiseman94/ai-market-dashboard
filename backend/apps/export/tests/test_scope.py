from __future__ import annotations

import zipfile

import pytest

from apps.export.models import ExportJob
from apps.export.services import build_export_bundle
from apps.threads.models import Thread


@pytest.mark.django_db
def test_scope_threads_subset(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))

    t1 = Thread.objects.create(kind="chat", title="Alpha")
    t2 = Thread.objects.create(kind="chat", title="Beta")

    job = ExportJob.objects.create(
        scope={"threads": [t1.id]},
        format="zip",
        status="pending",
    )
    build_export_bundle(job.id)
    job.refresh_from_db()

    with zipfile.ZipFile(tmp_path / job.filename) as zf:
        names = zf.namelist()
        assert any(f"threads/{t1.id}/meta.json" in n for n in names)
        assert not any(f"threads/{t2.id}/meta.json" in n for n in names)
