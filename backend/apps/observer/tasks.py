"""Celery wrappers around observer services."""

from __future__ import annotations

from celery import shared_task

# Side-effect imports: register batch + prediction + trigger + briefing tasks when
# autodiscover loads tasks.py (merged from the former predictions/triggers/briefing apps).
from apps.observer import tasks_batch as _tasks_batch  # noqa: F401
from apps.observer.briefing import tasks as _briefing_tasks  # noqa: F401
from apps.observer.predictions import tasks as _prediction_tasks  # noqa: F401
from apps.observer.services.run import run_observer
from apps.observer.triggers import tasks as _trigger_tasks  # noqa: F401


# at-most-once: the structured/consensus paths bill run_structured synchronously
# inside run_observer (the plain path delegates to the already-at-most-once
# run_ai_on_message.delay()). acks_late=False stops a worker-loss redelivery from
# re-capturing the snapshot + re-billing. A lost fire is covered by the next
# periodic fire. See apps/observer/tests/test_task_acks.py.
@shared_task(name="observer.run_observer", acks_late=False, reject_on_worker_lost=False)
def run_observer_task(schedule_id: int, force: bool = False) -> int | None:
    return run_observer(schedule_id, force=force)


@shared_task(name="observer.fire_close_relative_schedules")
def fire_close_relative_schedules() -> dict:
    from apps.observer.services.close_relative import fire_due_close_relative

    return fire_due_close_relative()
