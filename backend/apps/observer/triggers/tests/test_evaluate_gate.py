from unittest.mock import patch

import pytest
from freezegun import freeze_time

from apps.observer.models import EventTrigger
from apps.observer.triggers.tasks import evaluate_triggers
from apps.profiles.models import TradingProfile


def _trigger(profile, name, ticker):
    return EventTrigger.objects.create(
        profile=profile,
        name=name,
        condition={"metric": "price", "ticker": ticker, "op": ">", "value": 1},
    )


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_all_equity_triggers_skipped_off_hours():
    profile = TradingProfile.objects.create(name="p", style="s")
    _trigger(profile, "eq", "SPY")
    result = evaluate_triggers()
    assert result.get("skipped") == "all_markets_closed"


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday — crypto open
def test_crypto_trigger_is_evaluated_off_hours():
    profile = TradingProfile.objects.create(name="p", style="s")
    _trigger(profile, "eq", "SPY")
    crypto = _trigger(profile, "cx", "BTC-USD")
    with (
        patch("apps.observer.triggers.tasks.metrics.build_snapshot", return_value={}) as bs,
        patch("apps.observer.triggers.tasks.cooldown_blocks", return_value=False),
        patch("apps.observer.triggers.tasks.evaluator.evaluate", return_value=(False, {})),
        patch("apps.observer.triggers.tasks.mark_rearmed"),
    ):
        evaluate_triggers()
        passed = list(bs.call_args[0][0])
        assert passed == [crypto]  # equity trigger filtered out
