"""Celery app factory.

Imported by config/__init__.py so @shared_task registration works.
Task modules are autodiscovered from installed apps.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("ai_dashboard")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
