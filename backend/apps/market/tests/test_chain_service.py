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
def test_fetch_chain_normalizes_index_symbol():
    # A bare index ticker must reach Schwab as "$SPX" (the snapshot's chain 400
    # was a bare "SPX"); the persisted row + payload key off the canonical symbol.
    fake_resp = MagicMock()
    fake_resp.json.return_value = SCHWAB_RAW
    fake_client = MagicMock()
    fake_client.get_option_chain.return_value = fake_resp

    with (
        patch("apps.market.services.chain.get_schwab_client", return_value=fake_client),
        patch("apps.market.services.chain.cache.get_or_fetch") as fake_cache,
    ):
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        out = fetch_chain("spx")

    assert fake_client.get_option_chain.call_args.kwargs["symbol"] == "$SPX"
    assert out["ticker"] == "$SPX"
    assert OptionChainSnapshot.objects.filter(ticker="$SPX").count() == 1


@pytest.mark.django_db
def test_fetch_chain_bounds_expirations():
    # Unbounded requests return EVERY listed expiration (a $SPX chain stored
    # ~119k tokens of dailies in the audit); the fetch asks Schwab for a bounded
    # window instead, and the window is part of the cache key.
    from datetime import UTC, datetime, timedelta

    fake_resp = MagicMock()
    fake_resp.json.return_value = SCHWAB_RAW
    fake_client = MagicMock()
    fake_client.get_option_chain.return_value = fake_resp

    seen_keys: list[str] = []

    def _cache(key, *, ttl_seconds, fetcher):
        seen_keys.append(key)
        return fetcher()

    with (
        patch("apps.market.services.chain.get_schwab_client", return_value=fake_client),
        patch("apps.market.services.chain.cache.get_or_fetch", side_effect=_cache),
    ):
        fetch_chain("SPY")
        fetch_chain("SPY", within_days=30)

    today = datetime.now(UTC).date()
    kwargs = fake_client.get_option_chain.call_args_list[0].kwargs
    assert kwargs["from_date"] == today
    assert kwargs["to_date"] == today + timedelta(days=60)  # default window
    kwargs30 = fake_client.get_option_chain.call_args_list[1].kwargs
    assert kwargs30["to_date"] == today + timedelta(days=30)
    assert seen_keys[0] != seen_keys[1]  # window participates in the cache key


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
