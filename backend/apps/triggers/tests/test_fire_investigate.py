from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.snapshots.models import Snapshot
from apps.triggers.models import EventTrigger
from apps.triggers.tasks import _do_fire


@pytest.mark.django_db
def test_do_fire_passes_investigate_flag():
    """A trigger with investigate=True dispatches the AI run in investigation mode."""
    ProviderConfig.objects.create(
        provider="claude", api_key="sk", enabled=True, daily_cost_cap_usd=Decimal("10.00")
    )
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        investigate=True,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    snap = Snapshot.objects.create(profile=p, includes=["quotes"])
    with (
        patch("apps.triggers.tasks.capture", return_value=snap),
        patch("apps.triggers.tasks.serialize_for_ai", return_value="payload"),
        patch("apps.triggers.tasks.run_ai_on_message") as ai,
        patch("apps.triggers.tasks.notify"),
    ):
        _do_fire(trigger_id=t.id, matched_values={"price:SPY": 1.0})

    ai.delay.assert_called_once()
    assert ai.delay.call_args.kwargs["investigate"] is True


@pytest.mark.django_db
def test_do_fire_default_not_investigate():
    """A plain trigger dispatches a normal (non-investigation) run."""
    ProviderConfig.objects.create(
        provider="claude", api_key="sk", enabled=True, daily_cost_cap_usd=Decimal("10.00")
    )
    p = TradingProfile.objects.create(name="P", style="x", default_provider="claude")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 0},
    )
    snap = Snapshot.objects.create(profile=p, includes=["quotes"])
    with (
        patch("apps.triggers.tasks.capture", return_value=snap),
        patch("apps.triggers.tasks.serialize_for_ai", return_value="payload"),
        patch("apps.triggers.tasks.run_ai_on_message") as ai,
        patch("apps.triggers.tasks.notify"),
    ):
        _do_fire(trigger_id=t.id, matched_values={"price:SPY": 1.0})

    assert ai.delay.call_args.kwargs["investigate"] is False
