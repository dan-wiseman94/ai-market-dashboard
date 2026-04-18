"""Observer-domain models: ObserverSchedule + Notification."""
from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.profiles.models import TradingProfile


class ObserverSchedule(models.Model):
    """A scheduled observer fire definition. Owns the linked PeriodicTask."""

    MODE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("full", "Full payload"),
        ("diff", "Diff vs previous capture"),
    ]

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
    mode = models.CharField(
        max_length=8, choices=MODE_CHOICES, default="full",
        help_text="diff: feed AI only the delta vs the last ready snapshot.",
    )
    structured = models.BooleanField(
        default=False,
        help_text="When True, observer runs use messages.parse with the "
                  "ObservationReport schema instead of streaming text.",
    )
    use_batch = models.BooleanField(
        default=False,
        help_text="When True, fires submit a Messages Batch per watchlist "
                  "ticker instead of streaming. 50% cheaper; not interactive.",
    )
    last_batch_id = models.CharField(max_length=64, blank=True, default="")
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


class Notification(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("trigger", "Trigger"),
        ("observer_done", "Observer fired"),
        ("error", "Error"),
        ("cost_limit", "Cost limit"),
        ("backup", "Backup"),
    ]

    # Nullable for v1 (no user-auth surface yet). When auth lands, backfill or
    # default to the resolved user. The FK shape keeps the model multi-user-ready.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="notifications",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=500, blank=True, default="")
    meta = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["user", "read_at", "-created_at"])]
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"Notification({self.kind}: {self.title})"
