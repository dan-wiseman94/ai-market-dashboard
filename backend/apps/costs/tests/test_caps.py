# backend/apps/costs/tests/test_caps.py
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.costs.services import caps
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread


def _seed(pc, cost):
    t = Thread.objects.create(kind="chat", title="t")
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="done")
    AIRun.objects.create(
        message=m,
        provider=pc.provider,
        model="m",
        cost_usd=Decimal(str(cost)),
        latency_ms=1,
        status="done",
    )


@pytest.mark.django_db
def test_caps_zero_when_no_runs() -> None:
    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("10.00"))
    out = caps()
    row = next(r for r in out if r["provider"] == "claude")
    assert row["daily"]["cap"] == Decimal("10.00")
    assert row["daily"]["spent"] == Decimal("0")
    assert row["daily"]["pct"] == 0.0
    assert row["monthly"] is None


@pytest.mark.django_db
def test_daily_pct_over_100() -> None:
    pc = ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    _seed(pc, "0.60")
    _seed(pc, "0.70")
    out = caps()
    row = next(r for r in out if r["provider"] == "claude")
    assert row["daily"]["spent"] == Decimal("1.30")
    assert row["daily"]["pct"] == 1.0  # clamped


@pytest.mark.django_db
def test_monthly_cap_populated_when_set() -> None:
    pc = ProviderConfig.objects.create(
        provider="openai",
        daily_cost_cap_usd=Decimal("5.00"),
        monthly_cost_cap_usd=Decimal("100.00"),
    )
    _seed(pc, "25.00")
    out = caps()
    row = next(r for r in out if r["provider"] == "openai")
    assert row["monthly"]["cap"] == Decimal("100.00")
    assert row["monthly"]["spent"] == Decimal("25.00")
    assert row["monthly"]["pct"] == 0.25
