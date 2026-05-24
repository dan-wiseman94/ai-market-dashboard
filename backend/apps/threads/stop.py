"""Redis-backed stop flags for in-flight AI streams.

The stop endpoint runs in the web process; the streaming run executes in a worker.
A short-lived Redis key bridges them so the worker can abort generation early —
closing the upstream stream stops further token generation (and billing) — instead
of merely discarding the final write after the model has already finished.
"""

from __future__ import annotations

import contextlib

import redis
from django.conf import settings

_TTL_SECONDS = 600


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _key(message_id: int) -> str:
    return f"thread:stop:{message_id}"


def request_stop(message_id: int) -> None:
    # Best-effort: the DB status flip is still recorded by the caller.
    with contextlib.suppress(Exception):
        _redis().setex(_key(message_id), _TTL_SECONDS, "1")


def is_stop_requested(message_id: int) -> bool:
    try:
        return bool(_redis().exists(_key(message_id)))
    except Exception:
        return False


def clear_stop(message_id: int) -> None:
    with contextlib.suppress(Exception):
        _redis().delete(_key(message_id))
