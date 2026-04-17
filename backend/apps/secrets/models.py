"""Encrypted per-provider credential storage."""
from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils import timezone

from apps.secrets.fields import EncryptedJSONField


class ApiCredential(models.Model):
    """One row per third-party provider (schwab, news, ...)."""

    PROVIDER_CHOICES: ClassVar = [
        ("schwab", "Charles Schwab"),
        ("finnhub", "Finnhub"),
        ("marketaux", "Marketaux"),
    ]

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, unique=True)
    token = EncryptedJSONField(null=True, blank=True)  # full OAuth token dict or {"api_key": "..."}
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secrets_apicredential"

    def __str__(self) -> str:
        return f"{self.get_provider_display()} (expires: {self.expires_at or 'never'})"

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return True
        return timezone.now() >= self.expires_at
