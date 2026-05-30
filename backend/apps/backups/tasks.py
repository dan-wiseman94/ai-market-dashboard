from __future__ import annotations

from celery import shared_task

from apps.backups.services import perform_backup, verify_latest


@shared_task(
    name="backups.run_backup",
    autoretry_for=(),
    max_retries=0,
    # pg_dump allows up to 30 min (subprocess timeout=1800 in services.py).
    # Override the global 600s/660s limits so a large DB backup is not killed mid-dump.
    soft_time_limit=1800,
    time_limit=1860,
)
def run_backup(kind: str = "scheduled") -> int:
    rec = perform_backup(kind)
    return rec.id


@shared_task(
    name="backups.verify_latest",
    autoretry_for=(),
    max_retries=0,
    # pg_restore --list is fast but give it headroom; never kills backup slots.
    soft_time_limit=180,
    time_limit=240,
)
def run_verify_latest() -> dict:
    """Celery task wrapping verify_latest() for the weekly restore-drill beat entry."""
    return verify_latest()
