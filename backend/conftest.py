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
def _no_data_source_env_keys(settings):
    """Blank the data-source .env key fallback for every test.

    `DATA_SOURCE_ENV_KEYS` is populated from the developer's real environment (compose
    injects the local env file into the test container), so a machine with, say, a real
    FINNHUB_API_KEY would silently flip every "no credential → not configured / degrades
    to None" assertion. Tests that exercise the fallback set the mapping explicitly.
    """
    settings.DATA_SOURCE_ENV_KEYS = {}


@pytest.fixture
def api():
    """Anonymous DRF client (the API is auth-less by design — network isolation, not auth)."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def profile(db):
    """Generic TradingProfile for tests that need one structurally (FK anchor).

    Tests that assert specific field values define a local `profile` fixture,
    which shadows this one.
    """
    from apps.profiles.models import TradingProfile

    return TradingProfile.objects.create(name="Test Profile", style="swing")


@pytest.fixture
def mk_bar(db):
    """OHLCBar factory: a flat bar (open=high=low=close) unless high/low are given.

    A naive `ts` is coerced to UTC so call sites can pass bare datetimes.
    """
    from datetime import UTC

    from apps.market.models import OHLCBar

    def _mk_bar(ticker, ts, close, *, timeframe="1h", volume=1, high=None, low=None):
        return OHLCBar.objects.create(
            ticker=ticker,
            timeframe=timeframe,
            ts=ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts,
            open=close,
            high=high if high is not None else close,
            low=low if low is not None else close,
            close=close,
            volume=volume,
        )

    return _mk_bar


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
