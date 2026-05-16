from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import traceback
from datetime import datetime
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
        ts = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
        filename = f"{ts}.sql.gz"
        path = out_dir / filename

        # Map Django-side POSTGRES_* env vars onto libpq's PG* equivalents that
        # pg_dump consults. POSTGRES_PASSWORD is the docker-compose convention;
        # PGPASSWORD is what libpq actually reads.
        pg_host = os.environ.get("PGHOST") or os.environ.get("POSTGRES_HOST", "db")
        pg_user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER", "postgres")
        pg_db = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB", "postgres")
        pg_pw = os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")

        with path.open("wb") as fh:
            cmd = [
                "pg_dump",
                "-Fc",
                "-Z",
                "6",
                "-h",
                pg_host,
                "-U",
                pg_user,
                pg_db,
            ]
            env = os.environ.copy()
            if pg_pw:
                env["PGPASSWORD"] = pg_pw
            try:
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
