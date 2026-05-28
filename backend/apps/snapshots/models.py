"""Snapshot domain. A Snapshot is a captured market state + metadata."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.profiles.models import TradingProfile


class Snapshot(models.Model):
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]
    SOURCE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("manual", "Manual"),
        ("observer", "Observer"),
        ("trigger", "Trigger"),
        ("briefing", "Briefing"),
    ]

    profile = models.ForeignKey(TradingProfile, on_delete=models.PROTECT, related_name="snapshots")
    objective = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    # Free-text positions the user types in; the AI parses them (no broker fetch).
    manual_positions = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    includes = models.JSONField(default=list)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="manual")
    captured_at = models.DateTimeField(auto_now_add=True)
    market_state = models.JSONField(null=True, blank=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["-captured_at"])]
        ordering: ClassVar[list[str]] = ["-captured_at"]

    def __str__(self) -> str:
        return f"Snapshot #{self.pk} ({self.status})"


class SnapshotSection(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("quotes", "Quotes"),
        ("ohlc", "OHLC"),
        ("chain", "Option chain"),
        ("positions", "Positions"),
        ("breadth", "Market breadth"),
        ("news", "News"),
        ("notes", "User notes"),
        ("image", "Chart image"),
    ]
    SECTION_STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    snapshot = models.ForeignKey(Snapshot, on_delete=models.CASCADE, related_name="sections")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=SECTION_STATUS_CHOICES, default="pending")
    error = models.TextField(blank=True, default="")
    payload_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["snapshot", "kind"], name="uniq_snapshot_section"),
        ]

    def __str__(self) -> str:
        return f"{self.snapshot_id}:{self.kind} ({self.status})"


class SnapshotImage(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("client_capture", "Client capture"),
        ("server_render", "Server render"),
    ]

    snapshot = models.ForeignKey(
        Snapshot,
        on_delete=models.CASCADE,
        related_name="images",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    data = models.BinaryField()
    mime_type = models.CharField(max_length=32, default="image/png")
    caption = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self) -> str:
        return f"SnapshotImage({self.id}, {self.kind})"
