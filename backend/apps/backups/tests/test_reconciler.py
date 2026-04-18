from __future__ import annotations

from pathlib import Path

import pytest

from apps.backups.models import BackupRecord
from apps.backups.services import reconcile_disk


@pytest.mark.django_db
def test_reconciler_marks_missing_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    present = tmp_path / "present.sql.gz"
    present.write_bytes(b"x")
    BackupRecord.objects.create(
        filename=present.name, size_bytes=1, sha256="x" * 64,
        kind="scheduled", status="ok",
    )
    BackupRecord.objects.create(
        filename="gone.sql.gz", size_bytes=1, sha256="g" * 64,
        kind="scheduled", status="ok",
    )

    reconcile_disk()

    assert BackupRecord.objects.get(filename="present.sql.gz").status == "ok"
    assert BackupRecord.objects.get(filename="gone.sql.gz").status == "missing"
