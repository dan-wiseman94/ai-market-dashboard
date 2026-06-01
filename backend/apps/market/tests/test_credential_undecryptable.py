"""Every data-source reader must degrade (not raise) when its stored key can't be decrypted
(DJANGO_SECRET_KEY or the encryption salt changed since it was saved).

All of them route their credential fetch through apps.secrets.credentials.decrypt_token,
which catches InvalidToken. This guards the whole family in one place instead of relying on
each per-provider helper to remember the guard.
"""

from __future__ import annotations

import pytest
from django.db import connection

from apps.market.services import (
    alpaca,
    corporate_actions,
    events,
    fred,
    fundamentals,
    marketaux,
    news,
    polygon,
    tiingo,
    tradier,
    twelvedata,
)
from apps.secrets.models import ApiCredential

# (reader callable, provider, expected degraded return). alpaca returns a (key, secret)
# tuple; the rest return the api_key string — so the degraded value differs.
CASES = [
    (events._finnhub_api_key, "finnhub", None),
    (news._finnhub_api_key, "finnhub", None),
    (fundamentals._finnhub_api_key, "finnhub", None),
    (corporate_actions._finnhub_api_key, "finnhub", None),
    (tradier._api_key, "tradier", None),
    (tiingo._api_key, "tiingo", None),
    (polygon._api_key, "polygon", None),
    (twelvedata._api_key, "twelvedata", None),
    (fred._api_key, "fred", None),
    (marketaux._api_key, "marketaux", None),
    (alpaca._credentials, "alpaca", (None, None)),
]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fn,provider,expected", CASES, ids=[fn.__module__.rsplit(".", 1)[-1] for fn, _, _ in CASES]
)
def test_reader_degrades_on_undecryptable(fn, provider, expected):
    ApiCredential.objects.create(provider=provider, token={"api_key": "k", "api_secret": "s"})
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE provider = %s",
            [b"not-valid-fernet-ciphertext", provider],
        )
    assert fn() == expected
