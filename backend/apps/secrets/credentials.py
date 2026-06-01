"""Guarded read of an encrypted ApiCredential token.

`ApiCredential.token` is an `EncryptedJSONField` that decrypts in `from_db_value` *during*
the ORM fetch, so `ApiCredential.objects.get(...)` raises `cryptography.fernet.InvalidToken`
when the stored ciphertext no longer matches the current key (the `DJANGO_SECRET_KEY` or the
encryption salt changed since it was saved). Every data-source reader needs the key, so this
is the single place that fetches it — the guard lives here once instead of being re-derived
(and forgotten) in each per-provider helper.
"""

from __future__ import annotations

from cryptography.fernet import InvalidToken

from apps.secrets.models import ApiCredential


def decrypt_token(provider: str) -> dict | None:
    """The decrypted token dict for ``provider``, or ``None`` when there is no row OR the
    stored token can't be decrypted. Callers treat ``None`` as "not configured" and degrade.
    """
    try:
        cred = ApiCredential.objects.get(provider=provider)
    except (ApiCredential.DoesNotExist, InvalidToken):
        return None
    return cred.token or None
