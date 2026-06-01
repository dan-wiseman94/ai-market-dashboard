from __future__ import annotations

from typing import ClassVar

from django.db import models


class RegimeReading(models.Model):
    """One classified market-regime reading. Append-only; the latest row is the
    current regime (see services.compute.current_regime)."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    composite = models.CharField(max_length=20)  # "Risk-On" / "Neutral-Transitional" / "Risk-Off" / "Stress"
    axes = models.JSONField(default=dict)  # {"volatility": "Elevated", "trend": "Downtrend", ...}
    drivers = models.JSONField(default=list)  # ["VIX 24 (82%ile) — Elevated", ...]
    narrative = models.TextField(blank=True, default="")
    inputs = models.JSONField(default=dict)  # raw values, for reproducibility
    changed_axes = models.JSONField(default=list)  # axis names that flipped vs the prior reading

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"RegimeReading({self.composite} @ {self.created_at:%Y-%m-%d %H:%M})"
