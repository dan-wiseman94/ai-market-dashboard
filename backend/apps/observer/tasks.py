"""Celery wrappers around observer services."""

from __future__ import annotations

from celery import shared_task

# Side-effect import: registers poll_open_batches when autodiscover loads tasks.py.
from apps.observer import tasks_batch as _tasks_batch  # noqa: F401
from apps.observer.services.run import run_observer


@shared_task(name="observer.run_observer")
def run_observer_task(schedule_id: int) -> int | None:
    return run_observer(schedule_id)


@shared_task(name="observer.fire_close_relative_schedules")
def fire_close_relative_schedules() -> dict:
    from apps.observer.services.close_relative import fire_due_close_relative

    return fire_due_close_relative()
