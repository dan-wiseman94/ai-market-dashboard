"""Edge and failure paths in build_snapshot: upstream errors, missing volume,
corrupt Redis values, and the _redis() constructor — the defensive branches the
happy-path metrics tests don't reach."""

from unittest.mock import patch

import fakeredis
import pytest
import redis as redis_lib

from apps.observer.models import EventTrigger
from apps.observer.triggers.metrics import _redis, build_snapshot
from apps.profiles.models import TradingProfile


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


def _trigger(condition):
    p = TradingProfile.objects.create(name="P", style="x")
    return EventTrigger.objects.create(name="r", profile=p, condition=condition)


def test_redis_factory_builds_a_client_without_connecting():
    # _redis() is patched out in every other test; exercise the real constructor.
    assert isinstance(_redis(), redis_lib.Redis)


@pytest.mark.django_db
def test_quote_fetch_failure_is_swallowed(fake_redis):
    t = _trigger({"metric": "price", "ticker": "SPY", "op": ">", "value": 1})
    with patch("apps.observer.triggers.metrics.fetch_quotes", side_effect=RuntimeError("schwab down")):
        snap = build_snapshot([t])  # must not raise
    assert snap["price:SPY"] is None


@pytest.mark.django_db
def test_vix_crossing_reads_prior_from_redis(fake_redis):
    t = _trigger({"metric": "vix", "op": "crosses_above", "value": 20})
    fake_redis.setex("trigger:last:$VIX", 60, "19.0")
    with patch("apps.observer.triggers.metrics.fetch_quotes", return_value={"$VIX": {"last": 21.0}}):
        snap = build_snapshot([t])
    assert snap["_prior:vix"] == 19.0
    assert snap["vix"] == 21.0


@pytest.mark.django_db
def test_volume_z_none_when_quote_or_volume_absent(fake_redis):
    # Ticker absent from quotes -> _extract_volume returns None -> _volume_z returns None.
    t = _trigger({"metric": "volume_z", "ticker": "NVDA", "op": ">=", "value": 2.0, "window": "5m"})
    with patch("apps.observer.triggers.metrics.fetch_quotes", return_value={}):
        snap = build_snapshot([t])
    assert snap["volume_z:NVDA:5m"] is None


@pytest.mark.django_db
def test_volume_z_corrupt_baseline_returns_none(fake_redis):
    t = _trigger({"metric": "volume_z", "ticker": "NVDA", "op": ">=", "value": 2.0, "window": "5m"})
    # Seed a prior cumulative reading and a non-numeric entry in the rolling list.
    fake_redis.setex("trigger:volprev:NVDA", 1200, "1000000")
    fake_redis.lpush("trigger:volwin:NVDA:5m", "not-a-number")
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes",
        return_value={"NVDA": {"last": 5.0, "volume": 1_001_000}},
    ):
        snap = build_snapshot([t])
    assert snap["volume_z:NVDA:5m"] is None


@pytest.mark.django_db
def test_redis_get_failure_yields_none_prior(fake_redis):
    t = _trigger({"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550})
    with (
        patch.object(fake_redis, "get", side_effect=ConnectionError("redis down")),
        patch("apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 551.0}}),
    ):
        snap = build_snapshot([t])  # must not raise
    assert snap["_prior:price:SPY"] is None
    assert snap["price:SPY"] == 551.0


@pytest.mark.django_db
def test_non_numeric_redis_prior_is_treated_as_none(fake_redis):
    t = _trigger({"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550})
    fake_redis.setex("trigger:last:SPY", 60, "garbage")  # un-parseable prior
    with patch("apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 551.0}}):
        snap = build_snapshot([t])
    assert snap["_prior:price:SPY"] is None


@pytest.mark.django_db
def test_positions_fetch_failure_is_swallowed(fake_redis):
    t = _trigger({"metric": "position_pl", "op": "<", "value": -1000})
    with patch("apps.observer.triggers.metrics.fetch_positions", side_effect=RuntimeError("schwab down")):
        snap = build_snapshot([t])  # must not raise
    assert snap["position_pl"] is None


@pytest.mark.django_db
def test_position_pl_pct_is_ratio_of_pl_to_market_value(fake_redis):
    t = _trigger({"metric": "position_pl_pct", "op": ">", "value": 0.0})
    rows = [
        {"unrealized_pl": 150.0, "mkt_value": 1000.0},
        {"unrealized_pl": 50.0, "mkt_value": 1000.0},
    ]
    with patch("apps.observer.triggers.metrics.fetch_positions", return_value=rows):
        snap = build_snapshot([t])
    # (150 + 50) / (1000 + 1000) = 0.1
    assert snap["position_pl_pct"] == pytest.approx(0.1)


@pytest.mark.django_db
def test_position_pl_pct_none_when_no_market_value(fake_redis):
    t = _trigger({"metric": "position_pl_pct", "op": ">", "value": 0.0})
    with patch(
        "apps.observer.triggers.metrics.fetch_positions",
        return_value=[{"unrealized_pl": 0.0, "mkt_value": 0.0}],
    ):
        snap = build_snapshot([t])
    assert snap["position_pl_pct"] is None


@pytest.mark.django_db
def test_last_tick_at_write_failure_is_swallowed(fake_redis):
    # A position-only condition makes the last_tick_at setex (line 121) the first
    # write of the run, so patching setex to raise isolates that defensive branch.
    t = _trigger({"metric": "position_pl", "op": "<", "value": -1000})
    with (
        patch.object(fake_redis, "setex", side_effect=ConnectionError("redis down")),
        patch(
            "apps.observer.triggers.metrics.fetch_positions",
            return_value=[{"unrealized_pl": -50.0, "mkt_value": 100.0}],
        ),
    ):
        snap = build_snapshot([t])  # must not raise
    assert snap["position_pl"] == -50.0
