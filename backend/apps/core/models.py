"""Core app models."""

from __future__ import annotations

import logging
from typing import ClassVar

from django.db import models

logger = logging.getLogger(__name__)


class SystemSettings(models.Model):
    """Singleton (pk=1 via .load()) of runtime-tunable knobs, editable from the UI.

    Every field is NULLABLE: NULL means "inherit the corresponding Django setting / env
    default" (resolved by apps.core.runtime_config), so existing env-based and CI/test
    `override_settings` setups keep working until a value is explicitly set in the UI.
    These are all read at task-run / request time, so a change takes effect without a
    worker/beat restart — unlike the .env values they override.
    """

    # Data retention (days) — apps.core.tasks reads these at run.
    retention_ohlc_days = models.IntegerField(null=True, blank=True)
    retention_chain_days = models.IntegerField(null=True, blank=True)
    retention_notification_days = models.IntegerField(null=True, blank=True)
    retention_error_days = models.IntegerField(null=True, blank=True)

    # AI failover — apps.threads.tasks. (provider "" = explicit none; NULL = inherit.)
    ai_failover_enabled = models.BooleanField(null=True, blank=True)
    # null=True is intentional: NULL means "inherit the setting"; "" is an explicit
    # "no failover provider". blank="" alone can't express that distinction.
    ai_failover_provider = models.CharField(max_length=32, null=True, blank=True)  # noqa: DJ001

    # Observer response cache — apps.observer.services.run.
    observer_response_cache_enabled = models.BooleanField(null=True, blank=True)
    observer_response_cache_ttl_seconds = models.IntegerField(null=True, blank=True)

    # Scheduled eval harness (advanced) — apps.analytics.tasks.
    aieval_scheduled_enabled = models.BooleanField(null=True, blank=True)
    aieval_scheduled_model = models.CharField(max_length=100, null=True, blank=True)  # noqa: DJ001
    aieval_scheduled_horizon = models.IntegerField(null=True, blank=True)
    aieval_scheduled_limit = models.IntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_systemsettings"
        verbose_name_plural = "system settings"

    def __str__(self) -> str:
        return "SystemSettings (singleton)"

    @classmethod
    def load(cls) -> SystemSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


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
