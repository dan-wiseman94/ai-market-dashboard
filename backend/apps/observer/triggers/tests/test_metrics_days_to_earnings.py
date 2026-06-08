from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.observer.triggers.evaluator import evaluate, leaf_key
from apps.observer.triggers.metrics import build_snapshot
from apps.observer.triggers.services.describe import describe


def test_leaf_key_for_days_to_earnings():
    assert leaf_key({"metric": "days_to_earnings", "ticker": "NVDA"}) == "days_to_earnings:NVDA"


@pytest.mark.django_db
def test_build_snapshot_resolves_days_to_earnings():
    MarketEvent.objects.create(
        source="finnhub",
        external_id="EARN:NVDA:x",
        kind="earnings",
        ticker="NVDA",
        title="NVDA earnings",
        event_time=timezone.now() + timedelta(days=3),
    )
    cond = {"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 5}
    snap = build_snapshot([SimpleNamespace(condition=cond)])
    assert snap["days_to_earnings:NVDA"] == 3
    assert evaluate(cond, snap)[0] is True


@pytest.mark.django_db
def test_build_snapshot_days_to_earnings_unknown_is_none():
    cond = {"metric": "days_to_earnings", "ticker": "ZZZZ", "op": "<=", "value": 5}
    with pytest.MonkeyPatch.context() as mp:
        from apps.market.services import events

        mp.setattr(events, "fetch_earnings", lambda *a, **k: [])
        snap = build_snapshot([SimpleNamespace(condition=cond)])
    assert snap["days_to_earnings:ZZZZ"] is None
    assert evaluate(cond, snap)[0] is False


def test_describe_days_to_earnings():
    assert describe({"days_to_earnings:NVDA": 2}) == "NVDA earnings in 2d"
