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
    # Free-text current holdings the user types in; the AI parses them (no broker fetch).
    manual_positions = models.TextField(blank=True, default="")
    # Free-text candidate trades the user is weighing; the AI evaluates the entry case.
    candidate_positions = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    includes = models.JSONField(default=list)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="manual")
    captured_at = models.DateTimeField(auto_now_add=True)
    market_state = models.JSONField(null=True, blank=True)
    primary_ticker = models.CharField(max_length=16, null=True, blank=True, db_index=True)  # noqa: DJ001

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
        ("overnight", "Overnight board"),
        ("events", "Upcoming events"),
        ("fundamentals", "Company fundamentals"),
        ("macro", "Macro indicators"),
        ("filings", "SEC filings"),
        ("treasury", "Treasury rates"),
        ("vix", "VIX term structure"),
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
    # Bytes live on the /data volume (file_path) for new images — keeping
    # pg_dump small. NULL data + a file_path is the offloaded shape; rows may
    # instead keep in-DB bytes. Read via apps.snapshots.image_store.read_image_bytes.
    data = models.BinaryField(null=True, blank=True)
    file_path = models.CharField(max_length=512, blank=True, default="")
    mime_type = models.CharField(max_length=32, default="image/png")
    caption = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self) -> str:
        return f"SnapshotImage({self.id}, {self.kind})"


# Unlink the offloaded /data file when a SnapshotImage row goes away (instance
# delete OR cascade from a Snapshot delete). Connecting this signal also opts the
# model out of Django's fast-delete, so it fires on queryset .delete() too —
# otherwise the bytes leak on the volume forever.
from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=SnapshotImage)
def _unlink_snapshot_image_file(sender, instance, **kwargs) -> None:
    from apps.snapshots.image_store import delete_image_file

    delete_image_file(instance)
