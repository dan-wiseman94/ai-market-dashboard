"""Seed the evaluate_triggers PeriodicTask on first migrate."""
import json

from django.conf import settings
from django.db import migrations


def _tick_seconds():
    return getattr(settings, "TRIGGER_TICK_SECONDS", 10)


def seed_periodic_task(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=_tick_seconds(), period="seconds",
    )
    PeriodicTask.objects.update_or_create(
        name="triggers.evaluate_triggers",
        defaults={
            "task": "triggers.evaluate_triggers",
            "interval": interval,
            "enabled": True,
            "kwargs": json.dumps({}),
        },
    )


def remove_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="triggers.evaluate_triggers").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("triggers", "0002_triggerfiring"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_periodic_task, reverse_code=remove_periodic_task),
    ]
