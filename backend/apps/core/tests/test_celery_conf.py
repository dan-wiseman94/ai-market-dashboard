"""Celery worker tuning assertions."""

from __future__ import annotations

from config.celery import app


def test_worker_prefetch_multiplier_is_one():
    """With acks_late=True and long-running tasks (streaming AI runs, war-room
    debates, pg_dump), a worker must reserve only the task it is actively running —
    otherwise a wedged head-of-line task holds its prefetched siblings and delays
    short maintenance ticks. prefetch_multiplier=1 is the Celery-recommended setting
    for long acks_late tasks."""
    assert app.conf.worker_prefetch_multiplier == 1
