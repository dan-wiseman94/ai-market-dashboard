from unittest.mock import MagicMock

import fakeredis
import pytest

from apps.market import cache as cache_module


@pytest.fixture
def redis_fake(monkeypatch):
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


def test_get_or_fetch_hits_when_fresh(redis_fake):
    fetcher = MagicMock(return_value={"hello": "world"})
    v1 = cache_module.get_or_fetch("k1", ttl_seconds=10, fetcher=fetcher)
    v2 = cache_module.get_or_fetch("k1", ttl_seconds=10, fetcher=fetcher)
    assert v1 == {"hello": "world"}
    assert v2 == {"hello": "world"}
    fetcher.assert_called_once()


def test_get_or_fetch_refetches_after_expiry(redis_fake):
    fetcher = MagicMock(side_effect=[{"v": 1}, {"v": 2}])
    cache_module.get_or_fetch("k2", ttl_seconds=1, fetcher=fetcher)
    redis_fake.delete("k2")  # simulate expiry
    result = cache_module.get_or_fetch("k2", ttl_seconds=1, fetcher=fetcher)
    assert result == {"v": 2}
    assert fetcher.call_count == 2


def test_ttl_for_kind_returns_configured_values():
    assert cache_module.ttl_for_kind("quotes") == 5
    assert cache_module.ttl_for_kind("positions") == 10
    assert cache_module.ttl_for_kind("ohlc_1m") == 30
    assert cache_module.ttl_for_kind("ohlc_1d") == 3600
    assert cache_module.ttl_for_kind("news") == 300
    assert cache_module.ttl_for_kind("unknown-kind") == 30
