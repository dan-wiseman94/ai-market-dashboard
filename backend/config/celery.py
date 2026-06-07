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
# Exposed as a module constant so the registration guard
# (apps/core/tests/test_celery_registration.py) binds to the SAME list the app
# uses — a copied list would silently drift. Add new task modules here.
TASK_PACKAGES = [
    "apps.core",
    "apps.market",
    "apps.observer",
    "apps.snapshots",
    "apps.threads",
    "apps.backups",
    "apps.export",
    "apps.thesis",
    "apps.recall",
    "apps.analytics",
    "apps.book",
    "apps.strategy",
]
app.autodiscover_tasks(TASK_PACKAGES)

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
    "resolve-due-predictions": {
        "task": "observer.resolve_due_predictions",
        "schedule": 300.0,
    },
    "check-prediction-invalidations": {
        "task": "observer.check_prediction_invalidations",
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
    "refresh-corporate-actions-daily": {
        "task": "market.refresh_corporate_actions",
        "schedule": crontab(hour=8, minute=30),
    },
    "briefing-run-scheduled": {
        "task": "observer.briefing_run_scheduled",
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
        "task": "analytics.aieval_run_scheduled",
        "schedule": crontab(hour=5, minute=0, day_of_week=1),
    },
    "lessons-distill": {
        "task": "thesis.distill",
        "schedule": crontab(hour=5, minute=30),  # daily, after new post-mortems resolve
    },
    "regime-refresh-intraday": {
        "task": "strategy.regime_refresh",
        "schedule": crontab(minute="*/30"),  # market-hours guard is inside the task
    },
    "regime-refresh-preopen": {
        "task": "strategy.regime_refresh",
        "schedule": crontab(hour=13, minute=0),  # ~09:00 ET pre-open; forced
        "kwargs": {"force": True},
    },
    "book-snapshot-daily": {
        "task": "book.snapshot_daily",
        "schedule": crontab(hour=22, minute=45),  # after ingest-daily-bars (22:30)
    },
    "desk-sweep": {
        "task": "strategy.sweep",
        "schedule": crontab(minute="*/30"),  # opt-in gate is inside the task
    },
}
