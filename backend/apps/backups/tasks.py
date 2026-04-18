from __future__ import annotations

from celery import shared_task

from apps.backups.services import perform_backup


@shared_task(name="backups.run_backup", autoretry_for=(), max_retries=0)
def run_backup(kind: str = "scheduled") -> int:
    rec = perform_backup(kind)
    return rec.id
