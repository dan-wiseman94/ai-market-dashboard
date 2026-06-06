"""Per-thread WS event log — monotonic seq + a buffered tail in Redis.

Every ``thread.<id>`` event gets a per-thread ``seq``; the recent tail is kept in
a capped Redis list so a client that drops and reconnects with
``?since=<seq>`` can replay everything it missed (see ThreadConsumer). All
operations are best-effort: a Redis failure must never break live streaming, so
``record`` falls back to returning the payload unstamped and ``replay_since``
returns ``[]``.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any, cast

import redis
from django.conf import settings

_TTL_SECONDS = 3600
_MAX_EVENTS = 256


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _seq_key(thread_id: int) -> str:
    return f"thread:{thread_id}:wsseq"


def _log_key(thread_id: int) -> str:
    return f"thread:{thread_id}:wslog"


def record(thread_id: int, payload: dict) -> dict:
    """Stamp ``payload`` with the next per-thread ``seq`` and append to the tail.

    Returns the stamped payload (live broadcast should send *this*). Best-effort:
    if Redis is unavailable the original payload is returned without a ``seq``.
    """
    try:
        r = _redis()
        # redis-py's sync client returns a concrete int; its stubs type every command as
        # the sync/async ResponseT union, so cast away the Awaitable arm.
        seq = cast(int, r.incr(_seq_key(thread_id)))
        stamped = {**payload, "seq": seq}
        pipe = r.pipeline()
        pipe.expire(_seq_key(thread_id), _TTL_SECONDS)
        pipe.rpush(_log_key(thread_id), json.dumps(stamped))
        pipe.ltrim(_log_key(thread_id), -_MAX_EVENTS, -1)
        pipe.expire(_log_key(thread_id), _TTL_SECONDS)
        pipe.execute()
        return stamped
    except Exception:
        return payload


def replay_since(thread_id: int, since: int) -> list[dict]:
    """Buffered events with ``seq > since``, oldest first. Best-effort → ``[]``."""
    out: list[dict] = []
    with contextlib.suppress(Exception):
        for item in cast("list[Any]", _redis().lrange(_log_key(thread_id), 0, -1)):
            try:
                ev = json.loads(item)
            except (ValueError, TypeError):
                continue
            if int(ev.get("seq", 0)) > since:
                out.append(ev)
    return out
