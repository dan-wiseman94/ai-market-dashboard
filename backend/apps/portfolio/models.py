"""Portfolio domain — manually maintained position records.

This is strictly observational record-keeping. There is NO broker write path.
Users log their own positions; the system computes P&L off stored OHLC bars.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils import timezone


class Position(models.Model):
    DIRECTION_CHOICES: ClassVar = [("long", "Long"), ("short", "Short")]
    STATUS_CHOICES: ClassVar = [("open", "Open"), ("closed", "Closed")]

    ticker = models.CharField(max_length=16, db_index=True)
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES, default="long")
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    avg_cost = models.DecimalField(max_digits=14, decimal_places=4)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="open", db_index=True)
    note = models.TextField(blank=True, default="")
    # Linking edge to the second brain. SET_NULL so deleting a thesis doesn't delete the position.
    thesis = models.ForeignKey(
        "thesis.Thesis",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="positions",
    )
    profile = models.ForeignKey(
        "profiles.TradingProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="positions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["-opened_at"]
        indexes: ClassVar = [
            models.Index(fields=["status", "-opened_at"]),
            models.Index(fields=["ticker", "status"]),
        ]

    def __str__(self) -> str:
        return f"Position({self.ticker}, {self.direction}, {self.status})"

    def save(self, *args, **kwargs):
        self.ticker = (self.ticker or "").upper()
        super().save(*args, **kwargs)
