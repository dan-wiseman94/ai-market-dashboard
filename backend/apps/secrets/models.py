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


class SchwabAppConfig(models.Model):
    """App-level Schwab OAuth credentials (client_id + secret), encrypted at rest.

    Singleton (pk=1 via .load()). Lets the user configure Schwab through the UI instead of
    editing .env and recreating containers. Distinct from ApiCredential, which holds the
    per-user OAuth *token*; this holds the *app* registration credentials. Read via
    apps.secrets.schwab_oauth.schwab_app_credentials(), which falls back to the
    SCHWAB_CLIENT_ID / SCHWAB_CLIENT_SECRET env settings when this row is absent or blank.
    """

    # Stored as {"v": "<value>"} so the Fernet wrapper + JSON schema match ProviderConfig.
    _client_id = EncryptedJSONField(null=True, blank=True, db_column="client_id")
    _client_secret = EncryptedJSONField(null=True, blank=True, db_column="client_secret")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secrets_schwabappconfig"

    def __str__(self) -> str:
        return f"SchwabAppConfig (client_id {'set' if self.client_id else 'unset'})"

    @classmethod
    def load(cls) -> SchwabAppConfig:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def client_id(self) -> str:
        return (self._client_id or {}).get("v", "")

    @client_id.setter
    def client_id(self, value: str) -> None:
        self._client_id = {"v": value} if value else None

    @property
    def client_secret(self) -> str:
        return (self._client_secret or {}).get("v", "")

    @client_secret.setter
    def client_secret(self, value: str) -> None:
        self._client_secret = {"v": value} if value else None


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
    supports_tools = models.BooleanField(default=True)
    discovered_models = models.JSONField(default=list, blank=True)
    models_synced_at = models.DateTimeField(null=True, blank=True)
    daily_cost_cap_usd = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("10.00")
    )
    monthly_cost_cap_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secrets_providerconfig"

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({'on' if self.enabled else 'off'})"

    @property
    def api_key(self) -> str:
        return (self._api_key or {}).get("k", "")

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key = {"k": value} if value else None
