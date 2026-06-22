"""perform_restore / restore_db — the restore path must connect with the
container's real POSTGRES_* credentials (the Makefile's $PGHOST/$PGUSER were
always empty in-container), and must reject path traversal on the file name.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.backups.services import perform_restore


def _set_pg_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_USER", "ai_dashboard")
    monkeypatch.setenv("POSTGRES_DB", "ai_dashboard")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")
    # Mimic the container: the PG* names libpq reads are NOT set.
    for v in ("PGHOST", "PGUSER", "PGDATABASE", "PGPASSWORD"):
        monkeypatch.delenv(v, raising=False)


def test_perform_restore_connects_with_mapped_postgres_creds(tmp_path, monkeypatch) -> None:
    _set_pg_env(monkeypatch, tmp_path)
    dump = tmp_path / "2026-04-18-000000.sql.gz"
    dump.write_bytes(b"fake custom-format archive")

    with patch("apps.backups.services.subprocess.run", return_value=MagicMock(returncode=0)) as sub:
        path = perform_restore("2026-04-18-000000.sql.gz")

    assert path == dump
    argv, kwargs = sub.call_args[0][0], sub.call_args[1]
    assert argv[0] == "pg_restore"
    host = argv[argv.index("-h") + 1]
    user = argv[argv.index("-U") + 1]
    db = argv[argv.index("-d") + 1]
    # The old Makefile expanded these to '' in-container — the whole bug.
    assert (host, user, db) == ("db", "ai_dashboard", "ai_dashboard")
    assert "" not in (host, user, db)
    assert kwargs["env"]["PGPASSWORD"] == "s3cret"
    assert str(dump) in argv


def test_perform_restore_missing_file_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        perform_restore("does-not-exist.sql.gz")


@pytest.mark.parametrize("bad", ["../etc/passwd", "sub/dir.sql.gz", "..\\win", "a/../../b"])
def test_perform_restore_rejects_path_traversal(tmp_path, monkeypatch, bad) -> None:
    monkeypatch.setenv("BACKUPS_DIR", str(tmp_path))
    (tmp_path / "real.sql.gz").write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        perform_restore(bad)


def test_restore_db_command_invokes_perform_restore() -> None:
    with patch(
        "apps.backups.management.commands.restore_db.perform_restore",
        return_value=Path("/data/backups/x.sql.gz"),
    ) as pr:
        call_command("restore_db", "x.sql.gz")
    pr.assert_called_once_with("x.sql.gz")


def test_restore_db_command_missing_file_is_commanderror() -> None:
    with (
        patch(
            "apps.backups.management.commands.restore_db.perform_restore",
            side_effect=FileNotFoundError("nope"),
        ),
        pytest.raises(CommandError),
    ):
        call_command("restore_db", "nope.sql.gz")
