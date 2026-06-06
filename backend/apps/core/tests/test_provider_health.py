"""Tests for the cross-process provider auth-health marker."""

from unittest.mock import patch

import fakeredis
import pytest


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: client):
        yield client


def test_mark_read_clear_auth_error_round_trip(fake_redis):
    from apps.core import provider_health

    assert provider_health.auth_error("schwab") is None
    provider_health.mark_auth_error("schwab", "Schwab rejected the saved credential")
    assert provider_health.auth_error("schwab") == "Schwab rejected the saved credential"
    provider_health.clear_auth_error("schwab")
    assert provider_health.auth_error("schwab") is None


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
