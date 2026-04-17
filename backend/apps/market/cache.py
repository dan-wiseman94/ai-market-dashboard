"""Redis cache helpers for market data.

TTLs come from the design spec §5.2. Values are JSON-serialized.
"""
from __future__ import annotations

import json
from typing import Any, Callable

import redis
from django.conf import settings

_TTL: dict[str, int] = {
    "quotes": 5,
    "ohlc_1m": 30,
    "ohlc_5m": 120,
    "ohlc_15m": 300,
    "ohlc_1h": 900,
    "ohlc_1d": 3600,
    "chain": 15,
    "breadth": 30,
    "news": 300,
    "positions": 10,
    "context": 30,
}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def ttl_for_kind(kind: str) -> int:
    return _TTL.get(kind, 30)


def get_or_fetch(key: str, *, ttl_seconds: int, fetcher: Callable[[], Any]) -> Any:
    """Read JSON from Redis at key; if missing, call fetcher, store, return."""
    r = _redis()
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)
    value = fetcher()
    r.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    return value
