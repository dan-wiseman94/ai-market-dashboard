"""decrypt_token: the single guarded accessor for an encrypted ApiCredential token."""

from __future__ import annotations

import pytest
from django.db import connection

from apps.secrets.credentials import decrypt_token
from apps.secrets.models import ApiCredential


@pytest.mark.django_db
def test_returns_token_when_decryptable():
    ApiCredential.objects.create(provider="finnhub", token={"api_key": "k"})
    assert decrypt_token("finnhub") == {"api_key": "k"}


@pytest.mark.django_db
def test_returns_none_when_missing():
    assert decrypt_token("nope") is None


@pytest.mark.django_db
def test_returns_none_when_undecryptable():
    """Corrupt the stored ciphertext (raw SQL, literal names) so the current Fernet can't
    read it — decrypt_token must swallow InvalidToken and return None."""
    ApiCredential.objects.create(provider="finnhub", token={"api_key": "k"})
    assert ApiCredential._meta.db_table == "secrets_apicredential"
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE provider = %s",
            [b"not-valid-fernet-ciphertext", "finnhub"],
        )
    assert decrypt_token("finnhub") is None
