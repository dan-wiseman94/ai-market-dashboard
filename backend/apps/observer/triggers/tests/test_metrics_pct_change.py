"""pct_change metric: percent move vs the oldest sample still inside a true
sliding window (Redis sorted set of timestamp -> price).

The first tick has no prior sample and returns None; a later tick within the
window computes the delta vs the oldest in-window sample; once a sample ages out
past the window it is no longer used as the baseline.
"""

from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.models import EventTrigger
from apps.observer.triggers.metrics import build_snapshot
from apps.profiles.models import TradingProfile

COND = {"metric": "pct_change", "ticker": "SPY", "op": ">", "value": 0.01, "window": "5m"}
ZKEY = "trigger:windowz:SPY:5m"


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


def _trigger():
    p = TradingProfile.objects.create(name="P", style="x")
    return EventTrigger.objects.create(name="r", profile=p, condition=COND)


@pytest.mark.django_db
def test_pct_change_none_when_quote_missing(fake_redis):
    t = _trigger()
    with patch("apps.observer.triggers.metrics.fetch_quotes", return_value={}):
        snap = build_snapshot([t])
    assert snap["pct_change:SPY:5m"] is None


@pytest.mark.django_db
def test_pct_change_first_tick_seeds_baseline_and_returns_none(fake_redis):
    t = _trigger()
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 550.0}}
    ):
        snap = build_snapshot([t])
    # Cold start: no prior sample yet, so None — but a sample is now recorded.
    assert snap["pct_change:SPY:5m"] is None
    assert fake_redis.zcard(ZKEY) == 1


@pytest.mark.django_db
def test_pct_change_second_tick_computes_delta(fake_redis):
    t = _trigger()
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 550.0}}
    ):
        build_snapshot([t])  # seed baseline at 550
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 561.0}}
    ):
        snap = build_snapshot([t])
    # (561 - 550) / 550 = 0.02
    assert snap["pct_change:SPY:5m"] == pytest.approx((561.0 - 550.0) / 550.0)


@pytest.mark.django_db
def test_pct_change_guards_division_by_zero_prior(fake_redis):
    import time

    t = _trigger()
    ago = time.time() - 60  # within the 5m window
    fake_redis.zadd(ZKEY, {f"{ago:.6f}|0.0": ago})  # a zero prior must not raise
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 550.0}}
    ):
        snap = build_snapshot([t])
    assert snap["pct_change:SPY:5m"] is None


@pytest.mark.django_db
def test_pct_change_ignores_sample_older_than_window(fake_redis):
    # THE FIX: a baseline recorded 400s ago is outside the 5m (300s) window and
    # must NOT be used — the old single-key code held it for up to 2*window.
    import time

    t = _trigger()
    old = time.time() - 400
    fake_redis.zadd(ZKEY, {f"{old:.6f}|500.0": old})
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 561.0}}
    ):
        snap = build_snapshot([t])
    assert snap["pct_change:SPY:5m"] is None  # stale baseline ignored, no in-window prior


@pytest.mark.django_db
def test_pct_change_baseline_is_oldest_in_window_sample(fake_redis):
    import time

    t = _trigger()
    now = time.time()
    fake_redis.zadd(
        ZKEY,
        {f"{now - 120:.6f}|550.0": now - 120, f"{now - 30:.6f}|558.0": now - 30},
    )
    with patch(
        "apps.observer.triggers.metrics.fetch_quotes", return_value={"SPY": {"last": 561.0}}
    ):
        snap = build_snapshot([t])
    # baseline = the OLDEST in-window sample (550), not the most recent (558)
    assert snap["pct_change:SPY:5m"] == pytest.approx((561.0 - 550.0) / 550.0)
