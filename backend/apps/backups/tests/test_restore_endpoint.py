"""POST /api/backups/<pk>/restore/ — the most destructive endpoint in the app.

Every test patches ``perform_restore`` or ``subprocess.run``: nothing here may ever
restore a real database.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, override_settings

from apps.backups.models import BackupRecord
from apps.backups.services import RestoreFailed, scrub_pg_output
from apps.core.models import SystemSettings

pytestmark = pytest.mark.django_db


@pytest.fixture
def backup(tmp_path, monkeypatch) -> BackupRecord:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    f = tmp_path / "2026-04-18-023000.sql.gz"
    f.write_bytes(b"custom-format archive")
    return BackupRecord.objects.create(
        filename=f.name,
        size_bytes=f.stat().st_size,
        sha256="s" * 64,
        kind="scheduled",
        status="ok",
    )


def _post(backup: BackupRecord, body: dict | None = None):
    return Client().post(
        f"/api/backups/{backup.id}/restore/",
        data=body if body is not None else {},
        content_type="application/json",
    )


@pytest.fixture(autouse=True)
def _lock_is_free():
    """The Redis lock is a real round trip; keep it free and record release."""
    with (
        patch("apps.backups.views.acquire_lock", return_value=True) as acq,
        patch("apps.backups.views.release_lock") as rel,
    ):
        yield acq, rel


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_success_returns_shape_the_ui_needs(backup) -> None:
    with patch("apps.backups.views.perform_restore", return_value=Path("/x")) as pr:
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 200
    body = resp.json()
    pr.assert_called_once_with(backup.filename)
    assert body["restored"] is True
    assert body["backup_id"] == backup.id
    assert body["filename"] == backup.filename
    assert isinstance(body["duration_ms"], int)
    # The endpoint cannot stop worker/beat (no docker.sock in any container) — it must
    # say so rather than imply the CLI's quiesce step happened.
    assert body["workers_quiesced"] is False
    assert "reload-workers" in body["warning"]


@override_settings(RESTORE_FROM_UI_ENABLED=True)
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"confirm": ""},
        {"confirm": "2026-04-18-023000.sql"},
        {"confirm": "  2026-04-18-023000.sql.gz  "},
        {"confirm": "yes"},
        {"confirm": None},
    ],
)
def test_confirmation_must_match_the_filename_exactly(backup, body) -> None:
    with patch("apps.backups.views.perform_restore") as pr:
        resp = _post(backup, body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "confirmation_mismatch"
    assert resp.json()["expected"] == backup.filename
    pr.assert_not_called()


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_non_dict_body_is_a_mismatch_not_a_crash(backup) -> None:
    with patch("apps.backups.views.perform_restore") as pr:
        resp = Client().post(
            f"/api/backups/{backup.id}/restore/",
            data="[1, 2]",
            content_type="application/json",
        )
    assert resp.status_code == 400
    pr.assert_not_called()


@override_settings(RESTORE_FROM_UI_ENABLED=False)
def test_disabled_by_setting_returns_403(backup) -> None:
    with patch("apps.backups.views.perform_restore") as pr:
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "restore_disabled"
    assert "Settings" in body["detail"]
    pr.assert_not_called()


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_disabled_by_systemsettings_override_returns_403(backup) -> None:
    cfg = SystemSettings.load()
    cfg.restore_from_ui_enabled = False
    cfg.save()

    with patch("apps.backups.views.perform_restore") as pr:
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 403
    pr.assert_not_called()


@override_settings(RESTORE_FROM_UI_ENABLED=True)
@pytest.mark.parametrize("bad_status", ["failed", "rotated", "deleted", "missing"])
def test_only_an_ok_backup_restores(backup, bad_status) -> None:
    backup.status = bad_status
    backup.save(update_fields=["status"])

    with patch("apps.backups.views.perform_restore") as pr:
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 409
    assert resp.json()["code"] == "backup_not_restorable"
    pr.assert_not_called()


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_concurrent_backup_blocks_the_restore(backup, _lock_is_free) -> None:
    acq, _rel = _lock_is_free
    acq.return_value = False

    with patch("apps.backups.views.perform_restore") as pr:
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 409
    assert resp.json()["code"] == "backup_in_progress"
    pr.assert_not_called()


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_lock_is_released_when_the_restore_fails(backup, _lock_is_free) -> None:
    _acq, rel = _lock_is_free

    with patch(
        "apps.backups.views.perform_restore",
        side_effect=RestoreFailed(1, 'pg_restore: error: connection to "db" failed'),
    ):
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "restore_failed"
    assert body["exit_code"] == 1
    assert 'connection to "db" failed' in body["stderr"]
    rel.assert_called_once()


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_failure_body_never_carries_the_password(backup, monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "hunter2-super-secret")
    stderr = (
        "pg_restore: error: connection to server at db failed: "
        "FATAL: password authentication failed\n"
        "connection string: postgresql://ai_dashboard:hunter2-super-secret@db:5432/app"
    )
    with patch(
        "apps.backups.services.subprocess.run",
        return_value=MagicMock(returncode=1, stderr=stderr, stdout=""),
    ):
        resp = _post(backup, {"confirm": backup.filename})

    assert resp.status_code == 500
    assert "hunter2-super-secret" not in resp.content.decode()
    assert "***" in resp.json()["stderr"]


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_missing_file_on_disk_is_409_not_a_crash(backup, tmp_path) -> None:
    (tmp_path / backup.filename).unlink()
    resp = _post(backup, {"confirm": backup.filename})
    assert resp.status_code == 409
    assert resp.json()["code"] == "backup_file_missing"


@override_settings(RESTORE_FROM_UI_ENABLED=True)
def test_unknown_backup_is_404(db) -> None:
    resp = Client().post(
        "/api/backups/999999/restore/",
        data={"confirm": "whatever.sql.gz"},
        content_type="application/json",
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("raw", "password"),
    [
        ("postgresql://ai_dashboard:s3cret@db:5432/app", ""),
        ("postgres://u:p@db/app", ""),
        ("pg_restore: fetching https://x/y?api_key=abcd1234", ""),
        ("plain failure mentioning s3cret", "s3cret"),
    ],
)
def test_scrub_pg_output_masks_credentials(raw, password) -> None:
    out = scrub_pg_output(raw, password)
    for secret in ("s3cret", "abcd1234", ":p@"):
        assert secret not in out
    assert "***" in out


def test_scrub_pg_output_keeps_the_useful_part() -> None:
    out = scrub_pg_output("pg_restore: error: could not execute query: relation missing")
    assert out == "pg_restore: error: could not execute query: relation missing"
