"""Encrypted per-provider credential storage."""
from __future__ import annotations

from decimal import Decimal
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


class ProviderConfig(models.Model):
    """Knobs for a given AI provider. API key is Fernet-encrypted at rest.

    One row per provider — created on first settings write, read by apps.ai.
    """

    PROVIDER_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("claude", "Anthropic Claude"),
        ("openai", "OpenAI"),
        ("local", "Local (OpenAI-compatible)"),
    ]

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, unique=True)
    # api_key stored as EncryptedJSONField containing {"k": "<the key>"} so both
    # the Fernet wrapper and JSON schema stay the same as ApiCredential.token.
    _api_key = EncryptedJSONField(null=True, blank=True, db_column="api_key")
    base_url = models.CharField(max_length=255, blank=True, default="")
    default_model = models.CharField(max_length=100, blank=True, default="")
    enabled = models.BooleanField(default=True)
    supports_vision = models.BooleanField(default=True)
    daily_cost_cap_usd = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("10.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secrets_providerconfig"

    @property
    def api_key(self) -> str:
        return (self._api_key or {}).get("k", "") if self._api_key else ""

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = {"k": value} if value else None

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({'on' if self.enabled else 'off'})"
