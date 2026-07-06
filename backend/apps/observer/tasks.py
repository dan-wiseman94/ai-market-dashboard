"""Celery wrappers around observer services."""

from __future__ import annotations

import contextlib
import logging

import redis
from celery import shared_task
from django.conf import settings

# Side-effect imports: register batch + prediction + trigger + briefing tasks when
# autodiscover loads tasks.py.
from apps.observer import tasks_batch as _tasks_batch  # noqa: F401
from apps.observer.briefing import tasks as _briefing_tasks  # noqa: F401
from apps.observer.predictions import tasks as _prediction_tasks  # noqa: F401
from apps.observer.services.run import run_observer
from apps.observer.triggers import tasks as _trigger_tasks  # noqa: F401

log = logging.getLogger(__name__)

# Overlap guard: a user-authored cron interval shorter than the fire duration (slow
# free-provider fetches, structured/consensus API latency) would otherwise let two
# run_observer tasks execute in parallel for the same schedule on the concurrency>1
# worker — two captures, two AI runs (double billing), interleaved thread messages.
# Mirrors the trigger fire path's SET NX FIRE_LOCK. Released in finally so the next
# legitimate cron tick still fires; only *concurrent* overlap is suppressed.
FIRE_LOCK_KEY = "observer:fire:{schedule_id}"
FIRE_LOCK_TTL = 300  # seconds — covers a slow consensus / free-provider fire


# at-most-once: the structured/consensus paths bill run_structured synchronously
# inside run_observer (the plain path delegates to the already-at-most-once
# run_ai_on_message.delay()). acks_late=False stops a worker-loss redelivery from
# re-capturing the snapshot + re-billing. A lost fire is covered by the next
# periodic fire. See apps/observer/tests/test_task_acks.py.
@shared_task(name="observer.run_observer", acks_late=False, reject_on_worker_lost=False)
def run_observer_task(schedule_id: int) -> int | None:
    lock_key = FIRE_LOCK_KEY.format(schedule_id=schedule_id)
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        acquired = r.set(lock_key, "1", nx=True, ex=FIRE_LOCK_TTL)
    except redis.RedisError as exc:
        # The overlap guard is best-effort — if Redis is unreachable, still fire
        # (a rare overlap during an outage beats dropping the fire entirely).
        log.warning("observer %s: fire-lock unavailable (%s); firing unguarded", schedule_id, exc)
        return run_observer(schedule_id)
    if not acquired:
        log.warning("observer %s: fire already running; skipping overlap", schedule_id)
        return None
    try:
        return run_observer(schedule_id)
    finally:
        with contextlib.suppress(redis.RedisError):
            r.delete(lock_key)


@shared_task(name="observer.fire_close_relative_schedules")
def fire_close_relative_schedules() -> dict:
    from apps.observer.services.close_relative import fire_due_close_relative

    return fire_due_close_relative()
