"""Celery wrappers around observer services."""
from __future__ import annotations

from celery import shared_task

from apps.observer.services.run import run_observer


@shared_task(name="observer.run_observer")
def run_observer_task(schedule_id: int) -> int | None:
    return run_observer(schedule_id)
