"""Core app models."""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models

logger = logging.getLogger(__name__)


class ErrorEvent(models.Model):
    LEVELS: ClassVar[list[tuple[str, str]]] = [
        ("error", "Error"),
        ("warning", "Warning"),
        ("critical", "Critical"),
    ]

    level = models.CharField(max_length=16, choices=LEVELS, default="error", db_index=True)
    source = models.CharField(
        max_length=128, db_index=True
    )  # e.g. "celery.task:observer.run_observer"
    message = models.TextField()
    detail = models.JSONField(default=dict, blank=True)  # traceback (truncated), task args summary
    fingerprint = models.CharField(
        max_length=64, db_index=True, blank=True, default=""
    )  # for future dedup/grouping
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["resolved", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.level}] {self.source}: {self.message[:80]}"

    @classmethod
    def record(
        cls,
        level: str,
        source: str,
        message: str,
        detail: dict | None = None,
        fingerprint: str = "",
    ) -> ErrorEvent | None:
        """Create and persist an ErrorEvent.

        Wrapped so a failure to record NEVER raises — a recording failure
        must not cascade into the calling task/handler.
        """
        try:
            return cls.objects.create(
                level=level,
                source=source,
                message=message,
                detail=detail or {},
                fingerprint=fingerprint,
            )
        except Exception:
            logger.warning("error_event.record_failed", exc_info=True)
            return None
