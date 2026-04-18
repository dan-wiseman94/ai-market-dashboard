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
    ]
)

app.conf.beat_schedule = {
    "refresh-schwab-token-every-minute": {
        "task": "market.refresh_schwab_token",
        "schedule": crontab(minute="*"),
    },
}
