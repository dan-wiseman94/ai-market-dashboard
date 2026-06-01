"""Celery tasks for lesson distillation (M14 F2).

This module is registered EXPLICITLY in config/celery.py's autodiscover_tasks list
(this project does not autodiscover) — and worker/beat must be restarted to pick
up a new task. See CLAUDE.md.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(name="lessons.distill")
def distill() -> dict:
    from apps.lessons.services.distill import distill_lessons

    return distill_lessons()
