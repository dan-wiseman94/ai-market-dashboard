"""stop.py degrades safely when Redis is unavailable: is_stop_requested returns
False (don't abort a healthy stream just because the flag store is down)."""

from unittest.mock import MagicMock, patch

import redis as redis_lib

from apps.threads.stop import _redis, is_stop_requested


def test_redis_factory_builds_a_client_without_connecting():
    assert isinstance(_redis(), redis_lib.Redis)


def test_is_stop_requested_false_when_redis_raises():
    client = MagicMock()
    client.exists.side_effect = redis_lib.ConnectionError("redis down")
    with patch("apps.threads.stop._redis", return_value=client):
        assert is_stop_requested(123) is False
