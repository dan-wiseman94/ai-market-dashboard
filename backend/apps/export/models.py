from __future__ import annotations

from typing import ClassVar

from django.db import models


class ExportJob(models.Model):
    FORMAT_CHOICES: ClassVar[list[tuple[str, str]]] = [("zip", "zip")]
    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("done", "Done"),
        ("failed", "Failed"),
        ("deleted", "Deleted"),
        ("missing", "Missing"),
    ]

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    scope = models.JSONField()
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default="zip")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    filename = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
