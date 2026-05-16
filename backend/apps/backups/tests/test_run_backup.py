from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.backups.models import BackupRecord
from apps.backups.tasks import run_backup


@pytest.mark.django_db
def test_run_backup_creates_record_and_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    content = b"-- fake pg_dump output\n" * 100
    sha = hashlib.sha256(content).hexdigest()

    def fake_run(cmd, **kw):
        # Simulate pg_dump writing to the stdout path.
        dest = Path(kw["stdout"].name) if hasattr(kw["stdout"], "name") else None
        if dest:
            dest.write_bytes(content)
        return MagicMock(returncode=0)

    with (
        patch("apps.backups.services.subprocess.run", side_effect=fake_run) as sub,
        patch("apps.backups.services.acquire_lock", return_value=True),
        patch("apps.backups.services.release_lock"),
    ):
        run_backup(kind="manual")

    rec = BackupRecord.objects.get()
    assert rec.kind == "manual"
    assert rec.status == "ok"
    assert rec.size_bytes == len(content)
    assert rec.sha256 == sha
    # pg_dump args inspectable:
    args, _kwargs = sub.call_args
    assert "pg_dump" in args[0][0]


@pytest.mark.django_db
def test_run_backup_failure_records_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    def fake_run(cmd, **kw):
        raise RuntimeError("pg_dump failed: permission denied")

    with (
        patch("apps.backups.services.subprocess.run", side_effect=fake_run),
        patch("apps.backups.services.acquire_lock", return_value=True),
        patch("apps.backups.services.release_lock"),
    ):
        run_backup(kind="scheduled")

    rec = BackupRecord.objects.get()
    assert rec.status == "failed"
    assert "permission denied" in rec.error


@pytest.mark.django_db
def test_run_backup_lock_rejects_concurrent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    with patch("apps.backups.services.acquire_lock", return_value=False) as acq:
        run_backup(kind="manual")
        acq.assert_called_once()

    rec = BackupRecord.objects.get()
    assert rec.status == "failed"
    assert "already running" in rec.error
