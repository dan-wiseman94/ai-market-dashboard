"""Celery app factory.

Imported by config/__init__.py so @shared_task registration works.
Task modules are explicitly listed so discovery never silently drops a module
due to startup-ordering issues with Django's app registry.
"""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("ai_dashboard")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Explicit task packages: guarantees all task modules are registered even when
# autodiscover_tasks() is called before the full Django app registry is ready.
app.autodiscover_tasks(
    [
        "apps.core",
        "apps.market",
        "apps.observer",
        "apps.snapshots",
        "apps.threads",
        "apps.triggers",
        "apps.backups",
        "apps.export",
        "apps.thesis",
        "apps.briefing",
        "apps.recall",
        "apps.aieval",
    ]
)

app.conf.update(
    # A wedged provider stream or hung pg_dump must not pin a worker slot forever.
    task_soft_time_limit=600,  # 10 min: SoftTimeLimitExceeded (catchable cleanup)
    task_time_limit=660,  # 11 min: hard kill if soft limit ignored
    # Redelivery on worker crash (tasks are idempotent — see CLAUDE.md):
    #   postmortem: scheduled→running DB claim; triggers: Redis SET NX lock;
    #   backups: Redis acquire_lock() SET NX; observer: close_relative once-per-day guard.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Recycle workers to bound chromium/fastembed memory creep.
    worker_max_tasks_per_child=200,
    # Don't let the Redis result backend accumulate forever.
    result_expires=3600,
)

app.conf.beat_schedule = {
    "refresh-schwab-token-every-minute": {
        "task": "market.refresh_schwab_token",
        "schedule": crontab(minute="*"),
    },
    "poll-open-observer-batches": {
        "task": "observer.poll_open_batches",
        "schedule": 60.0,
    },
    "run-due-postmortems": {
        "task": "thesis.run_due_postmortems",
        "schedule": 300.0,
    },
    "fire-close-relative-schedules": {
        "task": "observer.fire_close_relative_schedules",
        "schedule": crontab(minute="*"),
    },
    "refresh-market-events-daily": {
        "task": "market.refresh_events",
        "schedule": crontab(hour=9, minute=0),
    },
    "briefing-run-scheduled": {
        "task": "briefing.run_scheduled",
        "schedule": crontab(minute="*/15"),
    },
    "recall-index-pending": {
        "task": "recall.index_pending",
        "schedule": crontab(minute="*/5"),
    },
    "ingest-daily-bars": {
        "task": "market.ingest_daily_bars",
        "schedule": crontab(hour=22, minute=30),
    },
    "prune-retention": {
        "task": "core.prune_retention",
        "schedule": crontab(hour=4, minute=0),  # daily 4am UTC, low-traffic window
    },
    "aieval-run-scheduled": {
        "task": "aieval.run_scheduled",
        "schedule": crontab(hour=5, minute=0, day_of_week=1),
    },
}
