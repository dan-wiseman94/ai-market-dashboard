"""Monthly cost cap must block like the daily cap does. Nullable cap means
'no monthly limit' — the existing code path on ProviderConfig stores None
when unset."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ai.cost import (
    CostCapExceededError,
    check_monthly_cap,
    monthly_spend_usd,
)
from apps.profiles.models import TradingProfile
from apps.threads.models import AIRun, Message, Thread


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="test", style="test")


@pytest.fixture
def thread(db, profile: TradingProfile) -> Thread:
    return Thread.objects.create(kind="consult", profile=profile)


def _make_run(thread: Thread, *, days_ago: int, cost: Decimal, provider: str = "claude") -> AIRun:
    msg = Message.objects.create(
        thread=thread, role="assistant", content={"text": ""}, status="done",
    )
    run = AIRun.objects.create(
        message=msg, provider=provider, model="claude-opus-4-7",
        cost_usd=cost, status="done",
    )
    AIRun.objects.filter(id=run.id).update(
        created_at=timezone.now() - timedelta(days=days_ago),
    )
    return run


def test_monthly_spend_sums_last_30_days(db, thread: Thread) -> None:
    _make_run(thread, days_ago=1, cost=Decimal("1.00"))
    _make_run(thread, days_ago=5, cost=Decimal("2.00"))
    _make_run(thread, days_ago=31, cost=Decimal("99.00"))  # outside window
    assert monthly_spend_usd("claude") == Decimal("3.00")


def test_check_monthly_cap_raises_when_exceeded(db, thread: Thread) -> None:
    _make_run(thread, days_ago=1, cost=Decimal("9.00"))
    with pytest.raises(CostCapExceededError):
        check_monthly_cap("claude", Decimal("10.00"), prospective_cost=Decimal("2.00"))


def test_check_monthly_cap_none_means_no_limit(db, thread: Thread) -> None:
    _make_run(thread, days_ago=1, cost=Decimal("1000.00"))
    check_monthly_cap("claude", None, prospective_cost=Decimal("1000.00"))


def test_check_monthly_cap_under_limit_passes(db, thread: Thread) -> None:
    _make_run(thread, days_ago=1, cost=Decimal("5.00"))
    check_monthly_cap("claude", Decimal("10.00"), prospective_cost=Decimal("2.00"))
