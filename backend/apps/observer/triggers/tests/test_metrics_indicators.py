from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.models import EventTrigger
from apps.observer.triggers import metrics
from apps.profiles.models import TradingProfile


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_rsi_leaf_computed(fake_redis, monkeypatch):
    rising = [
        {"high": c + 1, "low": c - 1, "close": float(c), "open": float(c)} for c in range(1, 60)
    ]
    monkeypatch.setattr("apps.observer.triggers.metrics.fetch_ohlc", lambda *a, **k: rising, raising=False)
    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_quotes",
        lambda *a, **k: {"NVDA": {"last": 60.0}},
    )
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    t = EventTrigger.objects.create(
        name="rsi",
        profile=p,
        condition={
            "metric": "rsi",
            "ticker": "NVDA",
            "window": "1d",
            "op": ">",
            "value": 70,
            "params": {"period": 14},
        },
    )
    snap = metrics.build_snapshot([t])
    assert snap["rsi:NVDA:1d:14"] is not None and snap["rsi:NVDA:1d:14"] > 70
