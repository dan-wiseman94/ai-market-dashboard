"""Analytics models.

EvalRun (offline calibration-harness results) lives here — eval calibration
belongs with the rest of the calibration analytics. ``db_table`` is pinned to
``aieval_evalrun`` (see migration 0001).
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class EvalRun(models.Model):
    SOURCE: ClassVar = [("manual", "Manual"), ("scheduled", "Scheduled")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=12, choices=SOURCE, default="manual")
    label = models.CharField(max_length=64, default="baseline")
    model = models.CharField(max_length=128, db_index=True)
    horizon = models.PositiveIntegerField(null=True, blank=True)

    n = models.PositiveIntegerField(default=0)
    skipped = models.PositiveIntegerField(default=0)
    scored = models.PositiveIntegerField(default=0)
    hit_rate = models.FloatField(null=True, blank=True)
    brier = models.FloatField(null=True, blank=True)
    avg_confidence = models.FloatField(null=True, blank=True)
    calibration_error = models.FloatField(null=True, blank=True)

    calibration = models.JSONField(default=list)
    examples = models.JSONField(default=list)

    class Meta:
        db_table = "aieval_evalrun"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["model", "-created_at"])]

    def __str__(self) -> str:
        return f"EvalRun(#{self.pk} {self.model} hit_rate={self.hit_rate})"
