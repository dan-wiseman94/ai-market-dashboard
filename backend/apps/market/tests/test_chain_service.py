from unittest.mock import MagicMock, patch

import pytest

from apps.market.models import OptionChainSnapshot
from apps.market.services.chain import fetch_chain

SCHWAB_RAW = {
    "underlyingPrice": 521.30,
    "callExpDateMap": {"2026-04-25:8": {"515.0": [{"strikePrice": 515.0, "bid": 7.20}]}},
    "putExpDateMap": {},
}


@pytest.mark.django_db
def test_fetch_chain_calls_schwab_and_persists():
    fake_resp = MagicMock()
    fake_resp.json.return_value = SCHWAB_RAW
    fake_client = MagicMock()
    fake_client.get_option_chain.return_value = fake_resp

    with (
        patch("apps.market.services.chain.get_schwab_client", return_value=fake_client),
        patch("apps.market.services.chain.cache.get_or_fetch") as fake_cache,
    ):
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        out = fetch_chain("SPY")

    assert out["underlying_last"] == "521.30"
    assert OptionChainSnapshot.objects.filter(ticker="SPY").count() == 1
    fake_client.get_option_chain.assert_called_once()


@pytest.mark.django_db
def test_fetch_chain_cache_hit_skips_schwab_and_persist():
    cached_payload = {"underlying_last": "100.00", "expiries": {}}
    with (
        patch("apps.market.services.chain.get_schwab_client") as fake_client_factory,
        patch("apps.market.services.chain.cache.get_or_fetch", return_value=cached_payload),
    ):
        out = fetch_chain("SPY")

    assert out == cached_payload
    fake_client_factory.assert_not_called()
    assert OptionChainSnapshot.objects.count() == 0
