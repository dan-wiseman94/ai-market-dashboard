"""Observer-domain models: ObserverSchedule + Notification."""
from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.profiles.models import TradingProfile


class ObserverSchedule(models.Model):
    """A scheduled observer fire definition. Owns the linked PeriodicTask."""

    name = models.CharField(max_length=100)
    profile = models.ForeignKey(
        TradingProfile, on_delete=models.CASCADE, related_name="observer_schedules",
    )
    enabled = models.BooleanField(default=True)
    market_hours_only = models.BooleanField(default=True)
    objective_template = models.TextField(blank=True, default="")
    override_provider = models.CharField(max_length=32, blank=True, default="")
    override_model = models.CharField(max_length=100, blank=True, default="")
    default_includes = models.JSONField(default=list)
    default_watchlist_tickers = models.JSONField(default=list)
    periodic_task = models.OneToOneField(
        "django_celery_beat.PeriodicTask",
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    last_fired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["profile", "enabled"])]

    def __str__(self) -> str:
        return f"ObserverSchedule({self.name})"
