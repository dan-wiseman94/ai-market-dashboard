"""event_log/stop reuse one module-level Redis client instead of building a fresh
client + ConnectionPool on every call.

record() runs once per streamed token and is_stop_requested() polls ~4x/sec for
each in-flight stream — the hottest paths in the app — so a per-call client+pool
construction churns connection pools/sockets. A cached singleton reuses one
bounded pool across calls.
"""

from __future__ import annotations

import redis as redis_lib

from apps.threads import event_log, stop


def test_event_log_redis_client_is_reused_across_calls():
    first = event_log._redis()
    assert first is event_log._redis()
    assert isinstance(first, redis_lib.Redis)


def test_stop_redis_client_is_reused_across_calls():
    first = stop._redis()
    assert first is stop._redis()
    assert isinstance(first, redis_lib.Redis)
