"""The Prediction Ledger (M13): the AI's own forecasts as first-class,
auto-resolving, calibration-tracked entities — symmetric to thesis/PostMortem.

A structured/consensus observer fire states a directional call
(``ObservationReport.predicted_direction`` et al.); ``apps.predictions`` promotes
that call into an ``AIPrediction`` row, resolves it against forward returns when
its horizon elapses, and scores it. This module only declares the model; the
extraction, resolution, analytics, and coach wiring live in services/tasks.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class AIPrediction(models.Model):
    DIRECTIONS: ClassVar = [
        ("bullish", "bullish"),
        ("bearish", "bearish"),
        ("neutral", "neutral"),
    ]
    STATUSES: ClassVar = [
        ("open", "open"),
        ("resolving", "resolving"),
        ("resolved", "resolved"),
        ("invalidated", "invalidated"),
    ]
    VERDICTS: ClassVar = [
        ("correct", "correct"),
        ("incorrect", "incorrect"),
        ("mixed", "mixed"),
        ("inconclusive", "inconclusive"),
    ]

    # --- What was called ---
    ticker = models.CharField(max_length=16, db_index=True)
    direction = models.CharField(max_length=8, choices=DIRECTIONS)
    horizon_days = models.PositiveIntegerField()
    confidence = models.FloatField()  # 0..1, stated by the model or the signal mean
    rationale = models.TextField(blank=True, default="")  # observation headline/summary
    invalidation_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    invalidation_note = models.CharField(max_length=300, blank=True, default="")

    # --- Who/what made it (provider/model are known directly — no thread attribution) ---
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

    # --- Lifecycle ---
    predicted_at = models.DateTimeField(db_index=True)
    resolve_at = models.DateTimeField(db_index=True)  # predicted_at + horizon (trading days)
    status = models.CharField(max_length=12, choices=STATUSES, default="open")

    # --- Outcome (filled at resolution) ---
    forward_return_pct = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=12, choices=VERDICTS, blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes: ClassVar = [
            models.Index(fields=["ticker", "status"]),
            models.Index(fields=["provider", "model", "status"]),
            models.Index(fields=["status", "resolve_at"]),  # the resolve_due beat scan
        ]

    def __str__(self) -> str:
        return f"AIPrediction({self.ticker}, {self.direction}, {self.horizon_days}d, {self.status})"
