"""``fire_observer_task`` (registered as ``observer.run_observer``) holds a
per-schedule Redis SET NX fire-lock so a cron interval shorter than the fire
duration can't run two overlapping fires for the same schedule (double capture +
double billing). Mirrors the trigger FIRE_LOCK.
"""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import redis as redis_lib

from apps.observer import tasks as obs_tasks


def test_overlap_guard_skips_when_lock_already_held() -> None:
    client = fakeredis.FakeStrictRedis()
    client.set(obs_tasks.FIRE_LOCK_KEY.format(schedule_id=123), "1")
    with (
        patch("apps.observer.tasks.redis.Redis.from_url", return_value=client),
        patch("apps.observer.tasks.fire_observer") as fire_observer,
    ):
        result = obs_tasks.fire_observer_task(123)

    fire_observer.assert_not_called()
    assert result is None


def test_overlap_guard_runs_and_releases_lock_when_free() -> None:
    client = fakeredis.FakeStrictRedis()
    with (
        patch("apps.observer.tasks.redis.Redis.from_url", return_value=client),
        patch("apps.observer.tasks.fire_observer", return_value=42) as fire_observer,
    ):
        result = obs_tasks.fire_observer_task(7)

    fire_observer.assert_called_once_with(7)
    assert result == 42
    # Lock released in finally so the next legitimate cron tick can fire.
    assert not client.exists(obs_tasks.FIRE_LOCK_KEY.format(schedule_id=7))


def test_overlap_guard_fires_unguarded_when_redis_unavailable() -> None:
    """The lock is best-effort — a Redis outage must not drop the fire entirely."""
    with (
        patch(
            "apps.observer.tasks.redis.Redis.from_url",
            side_effect=redis_lib.RedisError("down"),
        ),
        patch("apps.observer.tasks.fire_observer", return_value=9) as fire_observer,
    ):
        result = obs_tasks.fire_observer_task(1)

    fire_observer.assert_called_once_with(1)
    assert result == 9
