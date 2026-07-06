"""Observer-domain models: ObserverSchedule + Notification."""

from __future__ import annotations

from datetime import time
from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.core.model_bases import DirectionalCall, Resolution
from apps.profiles.models import TradingProfile


class ObserverSchedule(models.Model):
    """A scheduled observer fire definition. Owns the linked PeriodicTask."""

    MODE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("full", "Full payload"),
        ("diff", "Diff vs previous capture"),
    ]

    FIRE_MODE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("cron", "Cron"),
        ("relative_to_close", "Relative to close"),
    ]

    name = models.CharField(max_length=100)
    profile = models.ForeignKey(
        TradingProfile,
        on_delete=models.CASCADE,
        related_name="observer_schedules",
    )
    enabled = models.BooleanField(default=True)
    market_hours_only = models.BooleanField(default=True)
    objective_template = models.TextField(blank=True, default="")
    override_provider = models.CharField(max_length=32, blank=True, default="")
    override_model = models.CharField(max_length=100, blank=True, default="")
    default_includes = models.JSONField(default=list)
    default_watchlist_tickers = models.JSONField(default=list)
    mode = models.CharField(
        max_length=8,
        choices=MODE_CHOICES,
        default="full",
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
    consensus = models.BooleanField(
        default=False,
        help_text="When True (with structured), fan the ObservationReport across "
        "every structured-capable provider and record a cross-model agreement "
        "signal instead of a single structured report. ~Nx cost; opt-in only.",
    )
    investigate = models.BooleanField(
        default=False,
        help_text="When True (plain mode only), the fire runs a bounded tool-using "
        "investigation instead of a single observation.",
    )
    last_batch_id = models.CharField(max_length=64, blank=True, default="")
    fire_mode = models.CharField(max_length=20, choices=FIRE_MODE_CHOICES, default="cron")
    close_offset_minutes = models.PositiveIntegerField(
        default=5, help_text="Minutes before the actual session close to fire (relative_to_close)."
    )
    periodic_task = models.OneToOneField(
        "django_celery_beat.PeriodicTask",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
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
        ("postmortem", "Post-mortem"),
        ("briefing", "Briefing"),
        ("regime", "Regime"),
        ("book", "Book"),
        ("desk", "Desk"),
        ("cal_drift", "Calibration drift"),
        ("contra", "Consistency conflict"),
        ("pred_invalid", "Prediction invalidated"),
    ]

    # Nullable (no user-auth surface yet). When auth lands, backfill or
    # default to the resolved user. The FK shape keeps the model multi-user-ready.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
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


class AIPrediction(DirectionalCall, Resolution):
    """The Prediction Ledger: the AI's own auto-extracted, auto-resolving
    forecasts, promoted from observer fires (``services.run`` →
    ``predictions/services/extract``). ticker/direction/horizon_days/invalidation_*
    come from DirectionalCall; forward_return_pct/verdict from Resolution.
    ``db_table`` pinned.
    """

    STATUSES: ClassVar = [
        ("open", "open"),
        ("resolving", "resolving"),
        ("resolved", "resolved"),
        ("invalidated", "invalidated"),
    ]

    confidence = models.FloatField()  # 0..1
    # 1σ options-implied move (fraction) for this horizon, FROZEN at prediction time
    # from the snapshot's chain. None when no chain was captured. Scored at resolution
    # against |forward_return_pct| (within vs beyond what the options market priced).
    expected_move_pct = models.FloatField(null=True, blank=True)
    rationale = models.TextField(blank=True, default="")
    provider = models.CharField(max_length=32, db_index=True)
    model = models.CharField(max_length=64, db_index=True)
    source_message = models.ForeignKey(
        "threads.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_snapshot = models.ForeignKey(
        "snapshots.Snapshot", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    profile = models.ForeignKey(
        "profiles.TradingProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    predicted_at = models.DateTimeField(db_index=True)
    resolve_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="open")
    resolved_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "predictions_aiprediction"
        indexes: ClassVar = [
            models.Index(fields=["ticker", "status"]),
            models.Index(fields=["provider", "model", "status"]),
            models.Index(fields=["status", "resolve_at"]),
        ]

    def __str__(self) -> str:
        return f"AIPrediction({self.ticker}, {self.direction}, {self.horizon_days}d, {self.status})"


class EventTrigger(models.Model):
    """A user-defined condition rule; fires a snapshot + AI run when matched.
    db_table pinned.
    """

    name = models.CharField(max_length=100)
    profile = models.ForeignKey(
        "profiles.TradingProfile", on_delete=models.CASCADE, related_name="triggers"
    )
    condition = models.JSONField()
    cooldown_seconds = models.PositiveIntegerField(default=1800)
    enabled = models.BooleanField(default=True)
    investigate = models.BooleanField(
        default=False,
        help_text="When True, a fire runs a bounded tool-using investigation "
        "instead of a single observation.",
    )
    source_thesis = models.ForeignKey(
        "thesis.Thesis",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="guard_triggers",
    )
    last_fired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "triggers_eventtrigger"
        indexes: ClassVar = [models.Index(fields=["enabled", "-last_fired_at"])]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["profile", "name"], name="unique_trigger_name_per_profile"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (profile={self.profile_id})"

    def clean(self) -> None:
        from apps.observer.triggers.dsl import validate_condition

        validate_condition(self.condition)


class TriggerFiring(models.Model):
    """Immutable audit row: one per fire event."""

    trigger = models.ForeignKey(EventTrigger, on_delete=models.CASCADE, related_name="firings")
    fired_at = models.DateTimeField(auto_now_add=True)
    matched_values = models.JSONField()
    snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trigger_firings",
    )
    thread = models.ForeignKey(
        "threads.Thread",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trigger_firings",
    )
    cost_capped = models.BooleanField(default=False)

    class Meta:
        db_table = "triggers_triggerfiring"
        indexes: ClassVar = [
            models.Index(fields=["trigger", "-fired_at"]),
            models.Index(fields=["-fired_at"]),
        ]

    def __str__(self) -> str:
        return f"TriggerFiring(trigger={self.trigger_id}, fired_at={self.fired_at})"


class BriefingConfig(models.Model):
    """Singleton config for the daily Morning Briefing. Use load()."""

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

    class Meta:
        db_table = "briefing_briefingconfig"

    def __str__(self) -> str:
        return f"BriefingConfig(enabled={self.enabled}, send_at={self.send_at_local})"

    @classmethod
    def load(cls) -> BriefingConfig:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


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
        db_table = "briefing_briefingrun"
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"BriefingRun(#{self.pk} {self.status})"
