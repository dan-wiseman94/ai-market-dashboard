"""Tests for the cross-process provider auth-health marker."""

from unittest.mock import patch

import fakeredis
import pytest


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: client):
        yield client


def test_auth_error_is_per_provider(fake_redis):
    from apps.core import provider_health

    provider_health.mark_auth_error("schwab", "boom")
    assert provider_health.auth_error("schwab") == "boom"
    assert provider_health.auth_error("alpaca") is None


def test_auth_error_degrades_to_none_when_redis_unavailable():
    """A redis blip must never crash a read — degrade to "no known error"."""
    from apps.core import provider_health

    broken = fakeredis.FakeStrictRedis()

    def _boom(*_a, **_k):
        raise ConnectionError("redis down")

    broken.get = _boom  # type: ignore[method-assign]
    with patch("apps.core.provider_health._redis", lambda: broken):
        assert provider_health.auth_error("schwab") is None
