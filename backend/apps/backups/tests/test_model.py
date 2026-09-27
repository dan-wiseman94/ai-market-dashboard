from __future__ import annotations

import pytest

from apps.backups.models import BackupRecord


@pytest.mark.django_db
def test_backup_record_filename_unique() -> None:
    from django.db import IntegrityError

    BackupRecord.objects.create(
        filename="dup.sql.gz",
        size_bytes=1,
        sha256="x" * 64,
        kind="manual",
        status="ok",
    )
    with pytest.raises(IntegrityError):
        BackupRecord.objects.create(
            filename="dup.sql.gz",
            size_bytes=2,
            sha256="y" * 64,
            kind="scheduled",
            status="ok",
        )
