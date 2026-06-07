from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.models import EventTrigger
from apps.observer.triggers.metrics import build_snapshot
from apps.profiles.models import TradingProfile


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_position_pl_fetches_positions_once(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "position_pl", "op": "<", "value": -500},
    )
    with (
        patch("apps.observer.triggers.metrics.fetch_quotes") as fq,
        patch("apps.observer.triggers.metrics.fetch_positions") as fp,
    ):
        fq.return_value = {}
        fp.return_value = [
            {"ticker": "SPY", "unrealized_pl": -100.0, "mkt_value": 5000.0},
            {"ticker": "TSLA", "unrealized_pl": -400.0, "mkt_value": 3000.0},
        ]
        snap = build_snapshot([t])

    fp.assert_called_once()
    assert snap["position_pl"] == -500.0


@pytest.mark.django_db
def test_position_pl_pct_computed_from_totals(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "position_pl_pct", "op": "<", "value": -0.05},
    )
    with (
        patch("apps.observer.triggers.metrics.fetch_quotes") as fq,
        patch("apps.observer.triggers.metrics.fetch_positions") as fp,
    ):
        fq.return_value = {}
        fp.return_value = [
            {"ticker": "SPY", "unrealized_pl": -500.0, "mkt_value": 5000.0},
        ]
        snap = build_snapshot([t])

    assert snap["position_pl_pct"] == pytest.approx(-0.1)


@pytest.mark.django_db
def test_position_pl_pct_handles_zero_mkt_value(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "position_pl_pct", "op": "<", "value": -0.05},
    )
    with (
        patch("apps.observer.triggers.metrics.fetch_quotes") as fq,
        patch("apps.observer.triggers.metrics.fetch_positions") as fp,
    ):
        fq.return_value = {}
        fp.return_value = []  # no positions
        snap = build_snapshot([t])

    assert snap["position_pl_pct"] is None


@pytest.mark.django_db
def test_positions_failure_yields_none_metric(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "position_pl", "op": "<", "value": -500},
    )
    with (
        patch("apps.observer.triggers.metrics.fetch_quotes") as fq,
        patch("apps.observer.triggers.metrics.fetch_positions") as fp,
    ):
        fq.return_value = {}
        fp.side_effect = RuntimeError("schwab down")
        snap = build_snapshot([t])

    assert snap["position_pl"] is None
