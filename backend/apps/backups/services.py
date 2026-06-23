from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import traceback
from pathlib import Path

import redis
from django.conf import settings
from django.utils import timezone

from apps.backups.models import BackupRecord
from apps.observer.services.notifications import notify

log = logging.getLogger(__name__)

LOCK_KEY = "backup:running"
LOCK_TTL_S = 30 * 60


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.CELERY_BROKER_URL)


def acquire_lock() -> bool:
    return bool(_redis().set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_S))


def release_lock() -> None:
    from contextlib import suppress

    with suppress(Exception):
        _redis().delete(LOCK_KEY)


def backups_dir() -> Path:
    return Path(os.environ.get("BACKUPS_DIR", "/data/backups"))


def _sha256_stream(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _pg_conn() -> tuple[str, str, str, dict[str, str]]:
    """``(host, user, db, env)`` for pg_dump / pg_restore.

    Maps the docker-compose ``POSTGRES_*`` convention onto the ``PG*`` names libpq
    actually reads (``PGPASSWORD`` is what libpq consults). Shared by the backup
    writer and the restore path so they connect with the SAME credentials the
    container has — the Makefile cannot, since only ``POSTGRES_*`` is set in the
    container (``PGHOST``/``PGUSER``/``PGDATABASE`` are empty), which is why a
    Makefile-built ``pg_restore`` could never connect.
    """
    host = os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST", "db")
    user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER", "postgres")
    db = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB", "postgres")
    pw = os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")
    env = os.environ.copy()
    if pw:
        env["PGPASSWORD"] = pw
    return host, user, db, env


def perform_restore(filename: str) -> Path:
    """Restore the database from a pg_dump custom-format archive in ``backups_dir()``.

    Destructive: ``--clean --if-exists`` drops and recreates objects. Mirrors
    :func:`perform_backup`'s credential mapping (via :func:`_pg_conn`) so the
    restore connects with the container's real ``POSTGRES_*`` credentials.
    ``filename`` must be a bare name inside ``backups_dir()`` — a ``/`` or ``..``
    (path traversal) or a missing file raises ``FileNotFoundError``; a non-zero
    ``pg_restore`` exit raises ``subprocess.CalledProcessError``.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise FileNotFoundError(f"invalid backup name: {filename!r}")
    path = backups_dir() / filename
    if not path.is_file():
        raise FileNotFoundError(f"backup not found: {filename}")
    host, user, db, env = _pg_conn()
    cmd = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "-h",
        host,
        "-U",
        user,
        "-d",
        db,
        str(path),
    ]
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args -- list-args (no shell), trusted operator/db config; filename traversal-guarded above
    subprocess.run(cmd, check=True, timeout=1800, env=env)
    return path


def perform_backup(kind: str) -> BackupRecord:
    reconcile_disk()
    if not acquire_lock():
        msg = "another backup is already running"
        log.warning(msg)
        return BackupRecord.objects.create(
            filename=f"skipped-{timezone.now().strftime('%Y-%m-%d-%H%M%S')}.skipped",
            size_bytes=0,
            sha256="0" * 64,
            kind=kind,
            status="failed",
            error=msg,
        )

    try:
        out_dir = backups_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = timezone.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"{ts}.sql.gz"
        path = out_dir / filename

        pg_host, pg_user, pg_db, env = _pg_conn()

        with path.open("wb") as fh:
            cmd = ["pg_dump", "-Fc", "-Z", "6", "-h", pg_host, "-U", pg_user, pg_db]
            try:
                # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args -- list-args (no shell), trusted operator/db config; not external input
                subprocess.run(cmd, stdout=fh, check=True, timeout=1800, env=env)
            except Exception as e:
                path.unlink(missing_ok=True)
                rec = BackupRecord.objects.create(
                    filename=filename,
                    size_bytes=0,
                    sha256="0" * 64,
                    kind=kind,
                    status="failed",
                    error=str(e)[:4000],
                )
                notify(user_id=None, kind="backup", title="Backup failed", body=rec.error[:200])
                return rec

        sha = _sha256_stream(path)
        rec = BackupRecord.objects.create(
            filename=filename,
            size_bytes=path.stat().st_size,
            sha256=sha,
            kind=kind,
            status="ok",
        )
        notify(
            user_id=None,
            kind="backup",
            title=f"Backup complete: {filename}",
            body=f"{rec.size_bytes} bytes",
        )
        rotate_scheduled()
        return rec
    except Exception:
        tb = traceback.format_exc()[:4000]
        rec = BackupRecord.objects.create(
            filename=f"error-{timezone.now().strftime('%Y-%m-%d-%H%M%S')}.err",
            size_bytes=0,
            sha256="0" * 64,
            kind=kind,
            status="failed",
            error=tb,
        )
        notify(user_id=None, kind="backup", title="Backup failed", body=rec.error[:200])
        return rec
    finally:
        release_lock()


def rotate_scheduled(*, keep: int | None = None) -> None:
    """Delete scheduled backups beyond the keep-count. Manual backups untouched."""
    keep = keep if keep is not None else int(os.environ.get("BACKUPS_KEEP_SCHEDULED", "7"))
    recs = list(BackupRecord.objects.filter(kind="scheduled", status="ok").order_by("-created_at"))
    for rec in recs[keep:]:
        path = backups_dir() / rec.filename
        path.unlink(missing_ok=True)
        rec.status = "rotated"
        rec.save(update_fields=["status"])


def reconcile_disk() -> None:
    """Mark BackupRecord rows whose files are no longer on disk."""
    d = backups_dir()
    for rec in BackupRecord.objects.filter(status="ok"):
        if not (d / rec.filename).exists():
            rec.status = "missing"
            rec.save(update_fields=["status"])


def verify_latest() -> dict:
    """Restore-drill: run pg_restore --list on the newest successful backup to confirm
    it is restorable — not just byte-intact (sha256 proves the former, not the latter).

    Records a CRITICAL ErrorEvent on failure so it surfaces in /api/errors/.
    Never raises — always returns a dict.
    """
    rec = BackupRecord.objects.filter(status="ok").order_by("-created_at").first()
    if rec is None:
        return {"ok": False, "reason": "no_backup"}

    # Reconstruct the full path from backups_dir() + filename, mirroring how
    # perform_backup writes it (it never stores the full path on the model).
    path = backups_dir() / rec.filename

    try:
        # pg_restore --list reads the file directly — no DB connection needed.
        # It exits 0 and writes a table-of-contents to stdout if the file is a
        # valid custom-format dump; non-zero or empty stdout means corrupt.
        result = subprocess.run(
            ["pg_restore", "--list", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = result.returncode == 0 and bool(result.stdout.strip())
        err_detail: str | None = result.stderr.strip() if not ok else None
    except Exception as exc:
        ok = False
        err_detail = str(exc)

    if not ok:
        from apps.core.models import ErrorEvent

        ErrorEvent.record(
            level="critical",
            source="backups.verify_latest",
            message=f"Backup {rec.filename} failed restore-drill (pg_restore --list)",
            detail={"backup_id": rec.id, "filename": rec.filename, "error": err_detail},
            fingerprint="backups.verify_latest",
        )
        return {"ok": False, "filename": rec.filename, "backup_id": rec.id}

    return {"ok": True, "filename": rec.filename, "backup_id": rec.id}
