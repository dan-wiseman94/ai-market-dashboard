from __future__ import annotations

from typing import ClassVar

from django.db import models


class BackupRecord(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("scheduled", "Scheduled"),
        ("manual", "Manual"),
    ]
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("ok", "OK"),
        ("failed", "Failed"),
        ("rotated", "Rotated"),
        ("deleted", "Deleted"),
        ("missing", "Missing"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    filename = models.CharField(max_length=255, unique=True)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.filename} ({self.status})"
