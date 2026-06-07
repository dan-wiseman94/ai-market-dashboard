from decimal import Decimal

import pytest

from apps.ai.cost_reporting import cost_breakdown_today
from apps.profiles.models import TradingProfile
from apps.threads.models import AIRun, Message, Thread


@pytest.mark.django_db
def test_cost_breakdown_today_aggregates_by_provider():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m1 = Message.objects.create(thread=t, role="assistant", content={"text": "a"}, status="done")
    m2 = Message.objects.create(thread=t, role="assistant", content={"text": "b"}, status="done")
    m3 = Message.objects.create(thread=t, role="assistant", content={"text": "c"}, status="done")
    AIRun.objects.create(
        message=m1,
        provider="claude",
        model="claude-sonnet-4-6",
        cost_usd=Decimal("0.0100"),
        status="done",
        input_tokens=1000,
        output_tokens=500,
    )
    AIRun.objects.create(
        message=m2,
        provider="claude",
        model="claude-sonnet-4-6",
        cost_usd=Decimal("0.0200"),
        status="done",
        input_tokens=2000,
        output_tokens=1000,
    )
    AIRun.objects.create(
        message=m3,
        provider="openai",
        model="gpt-5",
        cost_usd=Decimal("0.0300"),
        status="done",
        input_tokens=500,
        output_tokens=200,
    )

    out = cost_breakdown_today()
    assert out["total_usd"] == Decimal("0.0600")
    claude = next(p for p in out["by_provider"] if p["provider"] == "claude")
    assert claude["cost_usd"] == Decimal("0.0300")
    assert claude["input_tokens"] == 3000
    assert claude["output_tokens"] == 1500
    assert claude["runs"] == 2
    openai = next(p for p in out["by_provider"] if p["provider"] == "openai")
    assert openai["cost_usd"] == Decimal("0.0300")
    assert openai["runs"] == 1
