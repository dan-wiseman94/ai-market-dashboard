from __future__ import annotations

from typing import ClassVar

from django.db import models


class BookSnapshot(models.Model):
    """One daily whole-book risk reading. Append-only; latest = current book."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    as_of_date = models.DateField(unique=True)
    exposures = models.JSONField(default=list)
    concentration = models.JSONField(default=dict)
    clusters = models.JSONField(default=list)
    regime_fit = models.JSONField(default=dict)
    near_invalidation = models.JSONField(default=list)
    narrative = models.TextField(blank=True, default="")
    coverage = models.JSONField(default=dict)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"BookSnapshot({self.as_of_date})"
