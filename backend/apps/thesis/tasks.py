"""Celery tasks for the post-mortem scheduler + replay."""

from __future__ import annotations

import structlog
from celery import shared_task
from django.utils import timezone

logger = structlog.get_logger(__name__)


@shared_task(name="thesis.run_postmortem")
def run_postmortem_task(pm_id: int) -> None:
    """Run a single post-mortem by id."""
    from .services.postmortem import run_postmortem

    run_postmortem(pm_id)


@shared_task(name="thesis.run_due_postmortems")
def run_due_postmortems() -> dict:
    """Beat-scheduled tick: dispatch every scheduled post-mortem now due.

    Mirrors the triggers.evaluate_triggers "select due rows, .delay() each"
    pattern. Returns a summary for logs.
    """
    from .models import PostMortem

    due = PostMortem.objects.filter(
        status="scheduled",
        due_at__lte=timezone.now(),
    ).values_list("id", flat=True)

    dispatched = 0
    for pm_id in due:
        run_postmortem_task.delay(pm_id)
        dispatched += 1

    logger.info("postmortem.tick", dispatched=dispatched)
    return {"dispatched": dispatched}


@shared_task(name="thesis.distill")
def distill() -> dict:
    """Cluster recurring lessons from decisive post-mortems (moved from the removed
    apps.lessons; renamed lessons.distill -> thesis.distill so the registration
    guard's name-prefix == owning-app convention holds).
    """
    from apps.thesis.services.lessons_distill import distill_lessons

    return distill_lessons()
