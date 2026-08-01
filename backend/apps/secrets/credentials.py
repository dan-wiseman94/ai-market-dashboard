"""Guarded read of an encrypted ApiCredential token.

`ApiCredential.token` is an `EncryptedJSONField` that decrypts in `from_db_value` *during*
the ORM fetch, so `ApiCredential.objects.get(...)` raises `cryptography.fernet.InvalidToken`
when the stored ciphertext no longer matches the current key (the `DJANGO_SECRET_KEY` or the
encryption salt changed since it was saved). Every data-source reader needs the key, so this
is the single place that fetches it — the guard lives here once instead of being re-derived
(and forgotten) in each per-provider helper.

DB rows die with the Docker volumes (`down -v` removes both the Postgres data and the /data
Fernet salt), so ``settings.DATA_SOURCE_ENV_KEYS`` backs each field from .env — the DB value
wins per-field, mirroring ``schwab_app_credentials``.
"""

from __future__ import annotations

from cryptography.fernet import InvalidToken
from django.conf import settings

from apps.secrets.models import ApiCredential


def env_token_fields(provider: str) -> dict:
    """The non-blank .env-provided credential fields for ``provider`` (empty for oauth /
    keyless sources, which have no ``DATA_SOURCE_ENV_KEYS`` entry)."""
    configured = settings.DATA_SOURCE_ENV_KEYS.get(provider, {})
    return {field: value for field, value in configured.items() if value}


def decrypt_token(provider: str) -> dict | None:
    """The effective token dict for ``provider``, or ``None`` when neither the DB nor .env
    holds a credential. A missing or undecryptable row degrades to the .env fields alone;
    callers treat ``None`` as "not configured" and degrade.
    """
    try:
        db_token = ApiCredential.objects.get(provider=provider).token or {}
    except (ApiCredential.DoesNotExist, InvalidToken):
        db_token = {}
    return {**env_token_fields(provider), **db_token} or None
