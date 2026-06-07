"""volume_z metric: z-score of per-tick interval volume against a rolling baseline.

Quote 'volume' is Schwab totalVolume (cumulative daily), so a spike detector must
work on per-interval deltas, not the raw cumulative figure.
"""

from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.models import EventTrigger
from apps.observer.triggers.metrics import _zscore, build_snapshot
from apps.profiles.models import TradingProfile

VOL_COND = {"metric": "volume_z", "ticker": "NVDA", "op": ">=", "value": 2.0, "window": "5m"}


def test_zscore_none_below_min_samples():
    assert _zscore(10.0, [10.0, 10.0]) is None


def test_zscore_none_when_flat():
    assert _zscore(5.0, [5.0, 5.0, 5.0, 5.0]) is None


def test_zscore_positive_for_spike():
    baseline = [1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 45000.0]
    z = _zscore(45000.0, baseline)
    assert z is not None
    assert z > 1.5


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_volume_z_cold_start_is_none(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition=VOL_COND)
    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"NVDA": {"last": 5.0, "volume": 1_000_000}}
        snap = build_snapshot([t])
    # First tick has no prior cumulative reading → no interval → None.
    assert snap["volume_z:NVDA:5m"] is None


@pytest.mark.django_db
def test_volume_z_detects_spike_after_baseline(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition=VOL_COND)
    # Steady ~1,000/interval cumulative volume, then a 45,000 jump on the last tick.
    cumulative = [1_000_000, 1_001_000, 1_002_000, 1_003_000, 1_004_000, 1_005_000, 1_050_000]
    z = None
    for vol in cumulative:
        with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
            fq.return_value = {"NVDA": {"last": 5.0, "volume": vol}}
            z = build_snapshot([t])["volume_z:NVDA:5m"]
    assert z is not None
    assert z > 1.5


@pytest.mark.django_db
def test_volume_z_handles_day_rollover(fake_redis):
    """Cumulative volume resetting (cur < prior) must not produce a negative interval."""
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition=VOL_COND)
    for vol in (5_000_000, 10_000):  # second reading is lower (new session)
        with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
            fq.return_value = {"NVDA": {"last": 5.0, "volume": vol}}
            snap = build_snapshot([t])
    assert snap["volume_z:NVDA:5m"] is None
