"""Tests for backups.services.verify_latest — restore-drill (M3-5)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.backups.models import BackupRecord
from apps.backups.services import verify_latest
from apps.core.models import ErrorEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(tmp_path, status: str = "ok") -> BackupRecord:
    """Create a BackupRecord whose filename lives under tmp_path.

    subprocess.run is always mocked in the tests that call this, so the file
    content doesn't matter — we just need a BackupRecord row with status="ok"
    and a filename that backups_dir() / filename resolves to (controlled via
    the BACKUPS_DIR env var monkeypatch).
    """
    p = tmp_path / "2026-01-01-000000.sql.gz"
    p.write_bytes(b"fake")
    return BackupRecord.objects.create(
        filename=p.name,
        size_bytes=4,
        sha256="a" * 64,
        kind="scheduled",
        status=status,
    )


# ---------------------------------------------------------------------------
# Case 1: no successful backups → ok=False, reason="no_backup"
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_verify_latest_no_backup_returns_no_backup() -> None:
    result = verify_latest()
    assert result == {"ok": False, "reason": "no_backup"}


@pytest.mark.django_db
def test_verify_latest_no_backup_only_failed_records(tmp_path, monkeypatch) -> None:
    """Even if there are failed records, still returns no_backup."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    BackupRecord.objects.create(
        filename="bad.sql.gz",
        size_bytes=0,
        sha256="0" * 64,
        kind="scheduled",
        status="failed",
        error="pg_dump failed",
    )
    result = verify_latest()
    assert result == {"ok": False, "reason": "no_backup"}


# ---------------------------------------------------------------------------
# Case 2: pg_restore --list succeeds → ok=True, no ErrorEvent created
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_verify_latest_success_returns_ok_dict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    rec = _make_record(tmp_path)

    good_result = SimpleNamespace(
        returncode=0, stdout="; Archive created by pg_dump\nsome content\n", stderr=""
    )

    with patch("apps.backups.services.subprocess.run", return_value=good_result) as mock_run:
        result = verify_latest()

    assert result == {"ok": True, "filename": rec.filename, "backup_id": rec.id}
    # Confirm subprocess was called with pg_restore --list
    args = mock_run.call_args[0][0]
    assert args[0] == "pg_restore"
    assert "--list" in args


@pytest.mark.django_db
def test_verify_latest_success_creates_no_error_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    _make_record(tmp_path)

    good_result = SimpleNamespace(returncode=0, stdout="toc line 1\ntoc line 2\n", stderr="")

    with patch("apps.backups.services.subprocess.run", return_value=good_result):
        verify_latest()

    assert ErrorEvent.objects.count() == 0


# ---------------------------------------------------------------------------
# Case 3: pg_restore --list fails (returncode=1) → ok=False + ErrorEvent created
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_verify_latest_failure_returncode_returns_not_ok(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    rec = _make_record(tmp_path)

    bad_result = SimpleNamespace(
        returncode=1, stdout="", stderr="pg_restore: error: invalid magic number"
    )

    with patch("apps.backups.services.subprocess.run", return_value=bad_result):
        result = verify_latest()

    assert result == {"ok": False, "filename": rec.filename, "backup_id": rec.id}


@pytest.mark.django_db
def test_verify_latest_failure_creates_critical_error_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    rec = _make_record(tmp_path)

    bad_result = SimpleNamespace(
        returncode=1, stdout="", stderr="pg_restore: error: invalid magic number"
    )

    with patch("apps.backups.services.subprocess.run", return_value=bad_result):
        verify_latest()

    assert ErrorEvent.objects.count() == 1
    ev = ErrorEvent.objects.get()
    assert ev.level == "critical"
    assert ev.source == "backups.verify_latest"
    assert ev.fingerprint == "backups.verify_latest"
    assert rec.filename in ev.message
    assert ev.detail["backup_id"] == rec.id
    assert ev.detail["filename"] == rec.filename


# ---------------------------------------------------------------------------
# Case 4: pg_restore returns 0 but empty stdout → treated as failure
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_verify_latest_empty_stdout_treated_as_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    _make_record(tmp_path)

    empty_result = SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("apps.backups.services.subprocess.run", return_value=empty_result):
        result = verify_latest()

    assert result["ok"] is False
    # An ErrorEvent should have been recorded
    assert ErrorEvent.objects.filter(source="backups.verify_latest").count() == 1


# ---------------------------------------------------------------------------
# Case 5: subprocess raises an exception → never propagates, returns dict + ErrorEvent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_verify_latest_subprocess_raises_never_propagates(tmp_path, monkeypatch) -> None:
    """verify_latest must NEVER raise, even when subprocess blows up."""
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    rec = _make_record(tmp_path)

    with patch("apps.backups.services.subprocess.run", side_effect=OSError("pg_restore not found")):
        result = verify_latest()  # must not raise

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["filename"] == rec.filename
    assert result["backup_id"] == rec.id


@pytest.mark.django_db
def test_verify_latest_subprocess_raises_creates_error_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    _make_record(tmp_path)

    with patch("apps.backups.services.subprocess.run", side_effect=OSError("pg_restore not found")):
        verify_latest()

    ev = ErrorEvent.objects.filter(source="backups.verify_latest").first()
    assert ev is not None
    assert ev.level == "critical"


# ---------------------------------------------------------------------------
# Case 6: picks the NEWEST ok record (not oldest)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_verify_latest_uses_newest_ok_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))

    # Create two ok records; the newer one has a distinct filename
    old_p = tmp_path / "2026-01-01-000000.sql.gz"
    old_p.write_bytes(b"old")
    BackupRecord.objects.create(
        filename=old_p.name, size_bytes=3, sha256="b" * 64, kind="scheduled", status="ok"
    )
    new_p = tmp_path / "2026-06-01-000000.sql.gz"
    new_p.write_bytes(b"new")
    new_rec = BackupRecord.objects.create(
        filename=new_p.name, size_bytes=3, sha256="c" * 64, kind="scheduled", status="ok"
    )

    good_result = SimpleNamespace(returncode=0, stdout="toc content\n", stderr="")

    with patch("apps.backups.services.subprocess.run", return_value=good_result):
        result = verify_latest()

    assert result["backup_id"] == new_rec.id
    assert result["filename"] == new_rec.filename
