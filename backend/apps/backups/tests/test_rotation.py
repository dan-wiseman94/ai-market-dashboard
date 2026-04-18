from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.backups.models import BackupRecord
from apps.backups.services import rotate_scheduled


@pytest.mark.django_db
def test_rotation_keeps_7_scheduled_and_all_manual(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    # 9 scheduled backups (newest = i=8), 2 manual
    for i in range(9):
        f = tmp_path / f"sched-{i}.sql.gz"
        f.write_bytes(b"x" * 10)
        r = BackupRecord.objects.create(
            filename=f.name, size_bytes=10, sha256="s" * 64,
            kind="scheduled", status="ok",
        )
        # space them out
        BackupRecord.objects.filter(pk=r.pk).update(
            created_at=timezone.now() - timedelta(days=10 - i),
        )
    for i in range(2):
        f = tmp_path / f"manual-{i}.sql.gz"
        f.write_bytes(b"y" * 10)
        BackupRecord.objects.create(
            filename=f.name, size_bytes=10, sha256="m" * 64,
            kind="manual", status="ok",
        )

    rotate_scheduled(keep=7)

    # Expect 7 scheduled "ok", 2 scheduled "rotated", both manuals "ok"
    assert BackupRecord.objects.filter(kind="scheduled", status="ok").count() == 7
    assert BackupRecord.objects.filter(kind="scheduled", status="rotated").count() == 2
    assert BackupRecord.objects.filter(kind="manual", status="ok").count() == 2
    # Rotated files gone from disk
    for rec in BackupRecord.objects.filter(status="rotated"):
        assert not (tmp_path / rec.filename).exists()
    # Kept files still present
    for rec in BackupRecord.objects.filter(kind="scheduled", status="ok"):
        assert (tmp_path / rec.filename).exists()
    for rec in BackupRecord.objects.filter(kind="manual"):
        assert (tmp_path / rec.filename).exists()
