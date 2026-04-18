from __future__ import annotations

from celery import shared_task

from apps.export.services import build_export_bundle


@shared_task(name="export.build_export", autoretry_for=(), max_retries=0)
def build_export(job_id: int) -> None:
    build_export_bundle(job_id)
