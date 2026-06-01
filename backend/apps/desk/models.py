from __future__ import annotations

from typing import ClassVar

from django.db import models


class DeskEntry(models.Model):
    STATUS_CHOICES: ClassVar = [("new", "New"), ("acted", "Acted"), ("dismissed", "Dismissed")]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    anomaly_type = models.CharField(max_length=32, db_index=True)
    ticker = models.CharField(
        max_length=16, blank=True, default="", db_index=True
    )  # "" = book-wide
    severity = models.FloatField(default=0.0)
    evidence = models.JSONField(default=dict)
    finding = models.TextField(blank=True, default="")
    suggested_actions = models.JSONField(default=list)  # [{"type","label","params"}]
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="new", db_index=True)
    warroom_run = models.ForeignKey(
        "warroom.WarRoomRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering: ClassVar = ["-created_at"]
        indexes: ClassVar = [models.Index(fields=["ticker", "anomaly_type", "-created_at"])]

    def __str__(self) -> str:
        return f"DeskEntry({self.anomaly_type} {self.ticker or 'book'})"
