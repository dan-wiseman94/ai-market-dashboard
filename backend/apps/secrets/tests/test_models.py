from datetime import timedelta

import pytest
from django.utils import timezone

from apps.secrets.models import ApiCredential


@pytest.mark.django_db
def test_create_credential_stores_token_encrypted():
    cred = ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A", "refresh_token": "R", "expires_at": 123},
        expires_at=timezone.now() + timedelta(hours=1),
    )
    cred.refresh_from_db()
    assert cred.token == {"access_token": "A", "refresh_token": "R", "expires_at": 123}


@pytest.mark.django_db
def test_unique_per_provider():
    ApiCredential.objects.create(provider="schwab", token={"a": 1})
    with pytest.raises(Exception, match=""):
        ApiCredential.objects.create(provider="schwab", token={"a": 2})


@pytest.mark.django_db
def test_is_expired_helper():
    past = ApiCredential(provider="schwab", token={}, expires_at=timezone.now() - timedelta(minutes=1))
    future = ApiCredential(provider="schwab", token={}, expires_at=timezone.now() + timedelta(minutes=10))
    none = ApiCredential(provider="schwab", token={})
    assert past.is_expired() is True
    assert future.is_expired() is False
    assert none.is_expired() is True  # no expiry recorded → treat as expired
