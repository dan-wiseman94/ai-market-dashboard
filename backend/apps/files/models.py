from __future__ import annotations

from typing import ClassVar

from django.db import models


class UserFile(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("filing", "SEC filing"),
        ("transcript", "Earnings transcript"),
        ("ohlc_csv", "Historical OHLC CSV"),
        ("research", "Research PDF"),
        ("other", "Other"),
    ]

    anthropic_id = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="other")
    ticker = models.CharField(max_length=16, blank=True, default="", db_index=True)
    mime = models.CharField(max_length=64, default="application/octet-stream")
    size = models.BigIntegerField(default=0)
    filename = models.CharField(max_length=200, blank=True, default="")
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"UserFile({self.anthropic_id}, {self.kind})"
