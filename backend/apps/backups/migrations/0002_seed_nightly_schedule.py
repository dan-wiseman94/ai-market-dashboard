from __future__ import annotations

from django.db import migrations


def seed(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    tz = "UTC"
    sched, _ = CrontabSchedule.objects.get_or_create(
        minute="30", hour="2", day_of_month="*", month_of_year="*", day_of_week="*",
        timezone=tz,
    )
    PeriodicTask.objects.get_or_create(
        name="backups.nightly",
        defaults={
            "crontab": sched,
            "task": "backups.run_backup",
            "kwargs": '{"kind": "scheduled"}',
            "enabled": True,
        },
    )


def unseed(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="backups.nightly").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("backups", "0001_initial"),
        ("django_celery_beat", "0001_initial"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
