from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.ai.cost_reporting import summary
from apps.threads.models import AIRun, Message, Thread


def _seed_run(thread, provider, model, cost, day_offset=0):
    msg = Message.objects.create(
        thread=thread, role="assistant", content={"text": ""}, status="done"
    )
    run = AIRun.objects.create(
        message=msg,
        provider=provider,
        model=model,
        cost_usd=Decimal(str(cost)),
        input_tokens=100,
        output_tokens=10,
        cached_tokens=50,
        latency_ms=100,
        status="done",
    )
    if day_offset:
        AIRun.objects.filter(pk=run.pk).update(
            created_at=datetime.now(tz=UTC) - timedelta(days=day_offset),
        )
    return run


@pytest.mark.django_db
def test_summary_aggregates_by_provider_and_model() -> None:
    t = Thread.objects.create(kind="chat", title="t")
    _seed_run(t, "claude", "claude-sonnet-4-6", "0.0100")
    _seed_run(t, "claude", "claude-sonnet-4-6", "0.0200")
    _seed_run(t, "openai", "gpt-5", "0.0050")

    now = datetime.now(tz=UTC)
    out = summary(start=now - timedelta(days=1), end=now + timedelta(hours=1))

    assert out["total"] == Decimal("0.0350")
    by_prov = {r["provider"]: r for r in out["by_provider"]}
    assert by_prov["claude"]["cost_usd"] == Decimal("0.0300")
    assert by_prov["openai"]["cost_usd"] == Decimal("0.0050")

    by_model = {r["model"]: r for r in out["by_model"]}
    assert by_model["claude-sonnet-4-6"]["cost_usd"] == Decimal("0.0300")
