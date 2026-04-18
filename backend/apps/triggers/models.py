"""EventTrigger + TriggerFiring models."""
from __future__ import annotations

from typing import ClassVar

from django.db import models


class EventTrigger(models.Model):
    """A user-defined condition rule; fires a snapshot + AI run when matched."""

    name = models.CharField(max_length=100)
    profile = models.ForeignKey(
        "profiles.TradingProfile", on_delete=models.CASCADE,
        related_name="triggers",
    )
    condition = models.JSONField()
    cooldown_seconds = models.PositiveIntegerField(default=1800)
    enabled = models.BooleanField(default=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["enabled", "-last_fired_at"])]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["profile", "name"],
                name="unique_trigger_name_per_profile",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (profile={self.profile_id})"
