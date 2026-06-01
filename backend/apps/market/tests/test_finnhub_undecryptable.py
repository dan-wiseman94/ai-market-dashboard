"""Regression: a finnhub ApiCredential whose token can't be decrypted (DJANGO_SECRET_KEY
or the encryption salt changed after it was saved) must degrade to "no key" rather than
raising cryptography.fernet.InvalidToken out of the fetchers.

Each market service has its own copy of `_finnhub_api_key()`; the decryption happens lazily
in EncryptedJSONField.from_db_value during the ORM fetch, so `ApiCredential.objects.get(...)`
raises before the caller can react unless the helper catches InvalidToken alongside
DoesNotExist.
"""

from __future__ import annotations

import pytest
from django.db import connection

from apps.market.services import corporate_actions, events, fundamentals, news
from apps.secrets.models import ApiCredential


@pytest.mark.django_db
@pytest.mark.parametrize("mod", [events, news, fundamentals, corporate_actions])
def test_finnhub_api_key_degrades_on_undecryptable(mod):
    ApiCredential.objects.create(provider="finnhub", token={"api_key": "real"})
    # Corrupt the stored ciphertext so the current Fernet can't read it (raw SQL with a
    # literal table/column name → no string interpolation; assert documents the names).
    assert ApiCredential._meta.db_table == "secrets_apicredential"
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE provider = %s",
            [b"not-valid-fernet-ciphertext", "finnhub"],
        )

    # Must return None (treated as "no key"), not raise InvalidToken.
    assert mod._finnhub_api_key() is None
