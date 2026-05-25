"""Thesis domain — a user's tracked directional call on a ticker."""

from __future__ import annotations

from typing import ClassVar

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Thesis(models.Model):
    DIRECTION_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("bullish", "Bullish"),
        ("bearish", "Bearish"),
        ("neutral", "Neutral"),
    ]
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("open", "Open"),
        ("closed_win", "Closed — Win"),
        ("closed_loss", "Closed — Loss"),
        ("closed_scratch", "Closed — Scratch"),
        ("invalidated", "Invalidated"),
    ]

    title = models.CharField(max_length=200)
    ticker = models.CharField(max_length=16)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    rationale = models.TextField(blank=True, default="")
    conviction = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )  # 1-5
    entry_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    invalidation_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    horizon_days = models.IntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")

    # FK references — all optional (SET_NULL) to survive related-object deletions
    profile = models.ForeignKey(
        "profiles.TradingProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theses",
    )
    thread = models.ForeignKey(
        "threads.Thread",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theses",
        help_text="Source thread from which this thesis was opened.",
    )
    snapshot = models.ForeignKey(
        "snapshots.Snapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theses",
        help_text="Market state at the time the thesis was opened.",
    )
    review_thread = models.ForeignKey(
        "threads.Thread",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_theses",
        help_text="Thread where post-mortems will be posted (Phase 2).",
    )

    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-opened_at"]
        indexes: ClassVar = [models.Index(fields=["status", "-opened_at"])]

    def __str__(self) -> str:
        return f"Thesis({self.ticker} {self.direction} {self.status})"

    def save(self, *args, **kwargs) -> None:
        self.ticker = (self.ticker or "").upper()
        super().save(*args, **kwargs)
