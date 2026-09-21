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
    retention_regime_days = models.IntegerField(null=True, blank=True)
    retention_desk_days = models.IntegerField(null=True, blank=True)
    retention_book_days = models.IntegerField(null=True, blank=True)

    # AI failover — apps.threads.tasks. (provider "" = explicit none; NULL = inherit.)
    ai_failover_enabled = models.BooleanField(null=True, blank=True)
    # Mirrors apps.secrets.ProviderConfig.PROVIDER_CHOICES plus the explicit "none".
    # Declared here rather than imported: apps.core must not import another app at
    # module load (apps/core/tests/test_layering.py). The API edge enforces this list
    # via views._check_column_limits, which reads the field's own choices — a provider
    # name added to ProviderConfig belongs here too, and in the apps.core.features row
    # for `ai.failover_provider` that renders the Settings → Features dropdown.
    FAILOVER_PROVIDER_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("", "None"),
        ("claude", "Anthropic Claude"),
        ("openai", "OpenAI"),
        ("local", "Local (OpenAI-compatible)"),
    ]
    # null=True is intentional: NULL means "inherit the setting"; "" is an explicit
    # "no failover provider". blank="" alone can't express that distinction.
    ai_failover_provider = models.CharField(  # noqa: DJ001
        max_length=32, null=True, blank=True, choices=FAILOVER_PROVIDER_CHOICES
    )

    # Observer response cache — apps.observer.services.run.
    observer_response_cache_enabled = models.BooleanField(null=True, blank=True)
    observer_response_cache_ttl_seconds = models.IntegerField(null=True, blank=True)

    # Scheduled eval harness (advanced) — apps.analytics.tasks.
    aieval_scheduled_enabled = models.BooleanField(null=True, blank=True)
    aieval_scheduled_model = models.CharField(max_length=100, null=True, blank=True)  # noqa: DJ001
    aieval_scheduled_horizon = models.IntegerField(null=True, blank=True)
    aieval_scheduled_limit = models.IntegerField(null=True, blank=True)

    # TradingView MCP tools for the in-app AI — apps.ai.tools.tradingview.
    tradingview_tools_enabled = models.BooleanField(null=True, blank=True)

    # Calibration-weighted routing fallback tier — apps.ai.router / apps.ai.structured.
    ai_calibration_routing_enabled = models.BooleanField(null=True, blank=True)
    # Daily calibration-drift notifier — apps.analytics.tasks.calibration_drift_sentinel.
    calibration_drift_sentinel_enabled = models.BooleanField(null=True, blank=True)
    # Beat-scheduled Desk anomaly sweep — apps.strategy.tasks.sweep.
    anomaly_sweep_enabled = models.BooleanField(null=True, blank=True)
    # Total-return (dividend-adjusted) forward-return math — apps.market.returns.
    returns_adjust_dividends = models.BooleanField(null=True, blank=True)

    # Autonomous investigation bounds — apps.threads.tasks.
    ai_investigation_max_iterations = models.IntegerField(null=True, blank=True)
    ai_autonomous_daily_cap_usd = models.FloatField(null=True, blank=True)

    # Calibration-routing eligibility floors — apps.ai.router.
    ai_calibration_routing_min_scored = models.IntegerField(null=True, blank=True)
    ai_calibration_routing_max_age_days = models.IntegerField(null=True, blank=True)

    # Restore-from-backup as a UI action — apps.backups.
    restore_from_ui_enabled = models.BooleanField(null=True, blank=True)
    # Chat tool-loop ceiling (non-investigation runs) — apps.threads.tasks.
    ai_chat_max_tool_iterations = models.IntegerField(null=True, blank=True)

    # AI prose layered on the deterministic daily readings. Off leaves the numbers
    # intact and drops only the paragraph — apps.strategy.regime / apps.book.
    regime_narrative_enabled = models.BooleanField(null=True, blank=True)
    book_narrative_enabled = models.BooleanField(null=True, blank=True)

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
