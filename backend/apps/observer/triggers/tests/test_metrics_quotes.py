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
def test_build_snapshot_collects_price_leaves(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={
            "all": [
                {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
                {"metric": "price", "ticker": "QQQ", "op": ">", "value": 480},
            ]
        },
    )

    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}, "QQQ": {"last": 481.0}}
        snap = build_snapshot([t])

    assert snap["price:SPY"] == 551.0
    assert snap["price:QQQ"] == 481.0
    fq.assert_called_once()
    tickers = (
        sorted(fq.call_args[0][0]) if fq.call_args[0] else sorted(fq.call_args.kwargs["tickers"])
    )
    assert tickers == ["QQQ", "SPY"]


@pytest.mark.django_db
def test_build_snapshot_stamps_redis_last_price(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        build_snapshot([t])

    assert fake_redis.get("trigger:last:SPY") == b"551.0"


@pytest.mark.django_db
def test_build_snapshot_populates_prior_for_crossings(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    fake_redis.setex("trigger:last:SPY", 60, "549.5")

    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550},
    )
    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        snap = build_snapshot([t])

    assert snap["_prior:price:SPY"] == 549.5
    assert snap["price:SPY"] == 551.0


@pytest.mark.django_db
def test_build_snapshot_missing_ticker_is_none(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "NOPE", "op": ">", "value": 1},
    )
    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {}
        snap = build_snapshot([t])

    assert snap["price:NOPE"] is None


@pytest.mark.django_db
def test_build_snapshot_vix_metric_fetches_vix_symbol(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "vix", "op": ">", "value": 20},
    )
    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"$VIX": {"last": 22.5}}
        snap = build_snapshot([t])

    tickers = (
        sorted(fq.call_args[0][0]) if fq.call_args[0] else sorted(fq.call_args.kwargs["tickers"])
    )
    assert "$VIX" in tickers
    assert snap["vix"] == 22.5


@pytest.mark.django_db
def test_build_snapshot_skips_positions_when_not_needed(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with (
        patch("apps.observer.triggers.metrics.fetch_quotes") as fq,
        patch("apps.observer.triggers.metrics.fetch_positions") as fp,
    ):
        fq.return_value = {"SPY": {"last": 551.0}}
        build_snapshot([t])

    fp.assert_not_called()


@pytest.mark.django_db
def test_build_snapshot_stamps_last_tick_at(fake_redis):
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    with patch("apps.observer.triggers.metrics.fetch_quotes") as fq:
        fq.return_value = {"SPY": {"last": 551.0}}
        build_snapshot([t])

    assert fake_redis.get("trigger:last_tick_at") is not None
