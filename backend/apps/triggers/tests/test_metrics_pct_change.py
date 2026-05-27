"""pct_change metric: percent move vs a windowed prior reading held in Redis.

The metric is a two-tick state machine — the first tick only seeds the windowed
baseline (returns None); the second tick reads it back and computes the delta.
"""

from unittest.mock import patch

import fakeredis
import pytest

from apps.profiles.models import TradingProfile
from apps.triggers.metrics import build_snapshot
from apps.triggers.models import EventTrigger

COND = {"metric": "pct_change", "ticker": "SPY", "op": ">", "value": 0.01, "window": "5m"}
WINDOW_KEY = "trigger:window:SPY:5m"


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.triggers.metrics._redis", return_value=client):
        yield client


def _trigger():
    p = TradingProfile.objects.create(name="P", style="x")
    return EventTrigger.objects.create(name="r", profile=p, condition=COND)


@pytest.mark.django_db
def test_pct_change_none_when_quote_missing(fake_redis):
    t = _trigger()
    with patch("apps.triggers.metrics.fetch_quotes", return_value={}):
        snap = build_snapshot([t])
    assert snap["pct_change:SPY:5m"] is None


@pytest.mark.django_db
def test_pct_change_first_tick_seeds_baseline_and_returns_none(fake_redis):
    t = _trigger()
    with patch("apps.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 550.0}}):
        snap = build_snapshot([t])
    # Cold start: no prior yet, so None — but the windowed baseline is now stored.
    assert snap["pct_change:SPY:5m"] is None
    assert fake_redis.get(WINDOW_KEY) == b"550.0"


@pytest.mark.django_db
def test_pct_change_second_tick_computes_delta(fake_redis):
    t = _trigger()
    with patch("apps.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 550.0}}):
        build_snapshot([t])  # seed baseline at 550
    with patch("apps.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 561.0}}):
        snap = build_snapshot([t])
    # (561 - 550) / 550 = 0.02
    assert snap["pct_change:SPY:5m"] == pytest.approx((561.0 - 550.0) / 550.0)


@pytest.mark.django_db
def test_pct_change_guards_division_by_zero_prior(fake_redis):
    t = _trigger()
    fake_redis.setex(WINDOW_KEY, 600, "0")  # a zero prior must not raise
    with patch("apps.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 550.0}}):
        snap = build_snapshot([t])
    assert snap["pct_change:SPY:5m"] is None
