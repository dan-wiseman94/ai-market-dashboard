from __future__ import annotations

import pytest

from apps.export.models import ExportJob
from apps.export.services import reconcile_export_disk


@pytest.mark.django_db
def test_export_reconciler_marks_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXPORTS_DIR", str(tmp_path))
    ExportJob.objects.create(
        scope={},
        format="zip",
        status="done",
        filename="gone.zip",
        size_bytes=1,
        sha256="g" * 64,
    )
    present = tmp_path / "present.zip"
    present.write_bytes(b"x")
    ExportJob.objects.create(
        scope={},
        format="zip",
        status="done",
        filename=present.name,
        size_bytes=1,
        sha256="p" * 64,
    )

    reconcile_export_disk()

    assert ExportJob.objects.get(filename="gone.zip").status == "missing"
    assert ExportJob.objects.get(filename="present.zip").status == "done"
