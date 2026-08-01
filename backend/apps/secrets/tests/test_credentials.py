"""decrypt_token: the single guarded accessor for an encrypted ApiCredential token."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import override_settings

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


# --- env fallback: DATA_SOURCE_ENV_KEYS backs a key when the DB can't ------------------
# DB rows (and the /data Fernet salt) die with `docker compose down -v`; .env survives.
# Mirrors schwab_app_credentials: DB value wins per-field, env fills the gaps.


@pytest.mark.django_db
@override_settings(DATA_SOURCE_ENV_KEYS={"finnhub": {"api_key": "env-k"}})
def test_env_fallback_when_no_row():
    assert decrypt_token("finnhub") == {"api_key": "env-k"}


@pytest.mark.django_db
@override_settings(DATA_SOURCE_ENV_KEYS={"finnhub": {"api_key": "env-k"}})
def test_db_row_wins_over_env():
    ApiCredential.objects.create(provider="finnhub", token={"api_key": "db-k"})
    assert decrypt_token("finnhub") == {"api_key": "db-k"}


@pytest.mark.django_db
@override_settings(DATA_SOURCE_ENV_KEYS={"alpaca": {"api_key": "env-k", "api_secret": "env-s"}})
def test_env_fills_fields_missing_from_db_row():
    ApiCredential.objects.create(provider="alpaca", token={"api_key": "db-k"})
    assert decrypt_token("alpaca") == {"api_key": "db-k", "api_secret": "env-s"}


@pytest.mark.django_db
@override_settings(DATA_SOURCE_ENV_KEYS={"finnhub": {"api_key": "env-k"}})
def test_env_fallback_when_row_undecryptable():
    ApiCredential.objects.create(provider="finnhub", token={"api_key": "db-k"})
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE provider = %s",
            [b"not-valid-fernet-ciphertext", "finnhub"],
        )
    assert decrypt_token("finnhub") == {"api_key": "env-k"}


@pytest.mark.django_db
@override_settings(DATA_SOURCE_ENV_KEYS={"finnhub": {"api_key": ""}})
def test_blank_env_value_is_not_a_credential():
    assert decrypt_token("finnhub") is None
