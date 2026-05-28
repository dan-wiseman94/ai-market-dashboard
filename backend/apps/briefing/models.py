"""Morning Briefing domain — singleton config + per-run record."""

from __future__ import annotations

from datetime import time
from typing import ClassVar

from django.db import models


class BriefingConfig(models.Model):
    """Singleton config for the daily briefing. Use BriefingConfig.load()."""

    enabled = models.BooleanField(default=True)
    send_at_local = models.TimeField(default=time(8, 30))
    profile = models.ForeignKey(
        "profiles.TradingProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    news_lookback_hours = models.PositiveIntegerField(default=14)
    events_within_days = models.PositiveIntegerField(default=7)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> "BriefingConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return f"BriefingConfig(enabled={self.enabled}, send_at={self.send_at_local})"


class BriefingRun(models.Model):
    STATUS: ClassVar = [("assembling", "Assembling"), ("ready", "Ready"), ("failed", "Failed")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default="assembling")
    data = models.JSONField(default=dict)
    snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    synthesis_message = models.ForeignKey(
        "threads.Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    scheduled_date = models.DateField(null=True, blank=True, unique=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"BriefingRun(#{self.pk} {self.status})"
