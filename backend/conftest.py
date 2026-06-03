"""Backend-wide pytest fixtures (collected for every test under backend/)."""

import pytest
from hypothesis import HealthCheck, settings

# Hypothesis runs many examples per test; under pytest-xdist the box is CPU-saturated,
# so a per-example wall-clock deadline produces spurious DeadlineExceeded flakes
# (e.g. tiktoken token-counting in the token-budget properties). Disable the deadline
# and the too-slow health check — correctness, not latency, is what these assert.
settings.register_profile("default", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("default")


@pytest.fixture(autouse=True)
def _reset_calendar_resolution_cache():
    """Isolate the per-process market-calendar resolution cache between tests.

    `apps.market.calendar.resolve._cache` maps ticker -> market key and is invalidated
    only by CalendarOverride.save()/delete() (correct in production). In tests, each
    test's DB rolls back WITHOUT firing those signals, so a CalendarOverride created in
    one test leaves a stale cache entry that poisons later tests — flipping ticker→
    market resolution and, through it, market-hours/trigger gates and heuristic
    assertions. pytest-randomly surfaced this as cross-app order-dependence. Clearing
    the cache around every test makes resolution hermetic regardless of order.
    """
    from apps.market.calendar.resolve import clear_resolution_cache

    clear_resolution_cache()
    yield
    clear_resolution_cache()


@pytest.fixture(autouse=True)
def _reset_channel_layers():
    """Give every test a fresh channel layer.

    `channels.layers.channel_layers` caches one backend instance per process. That
    singleton holds in-memory group/message state (InMemoryChannelLayer) and binds its
    async primitives to the first event loop that touches it. With pytest-randomly
    reordering function-scoped async tests, a layer populated/bound in one test then
    leaks messages — or a stale event loop — into the next, flaking consumer/run_ai/
    event_log tests. Clearing the backend cache forces a clean layer per test.
    """
    from channels.layers import channel_layers

    channel_layers.backends.clear()
    yield
    channel_layers.backends.clear()
