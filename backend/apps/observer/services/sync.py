"""Sync ObserverSchedule rows to django_celery_beat PeriodicTask rows."""
from __future__ import annotations

import json

from django.conf import settings
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.observer.models import ObserverSchedule


def sync_periodic_task(schedule: ObserverSchedule, *, cron: str) -> PeriodicTask:
    """Create or update the linked PeriodicTask from a 5-field cron expression."""
    minute, hour, dom, month, dow = cron.split()
    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=minute, hour=hour, day_of_month=dom,
        month_of_year=month, day_of_week=dow,
        timezone=settings.OBSERVER_BEAT_TIMEZONE,
    )
    if schedule.periodic_task is None:
        pt = PeriodicTask.objects.create(
            name=f"observer-schedule-{schedule.id}",
            task="observer.run_observer",
            crontab=crontab,
            kwargs=json.dumps({"schedule_id": schedule.id}),
            enabled=schedule.enabled,
        )
        schedule.periodic_task = pt
        schedule.save(update_fields=["periodic_task"])
    else:
        pt = schedule.periodic_task
        pt.crontab = crontab
        pt.enabled = schedule.enabled
        pt.kwargs = json.dumps({"schedule_id": schedule.id})
        pt.save()
    return pt


def delete_periodic_task(schedule: ObserverSchedule) -> None:
    """Remove the linked PeriodicTask. Leaves CrontabSchedule (potentially shared)."""
    if schedule.periodic_task_id:
        schedule.periodic_task.delete()
