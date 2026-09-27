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
