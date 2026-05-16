from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.costs.services import csv_rows
from apps.threads.models import AIRun, Message, Thread


@pytest.mark.django_db
def test_csv_rows_yields_header_then_data() -> None:
    t = Thread.objects.create(kind="chat", title="t")
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="done")
    AIRun.objects.create(
        message=m,
        provider="claude",
        model="claude-sonnet-4-6",
        cost_usd=Decimal("0.0123"),
        input_tokens=100,
        output_tokens=10,
        cached_tokens=50,
        latency_ms=500,
        status="done",
    )
    now = datetime.now(tz=UTC)
    rows = list(csv_rows(start=now - timedelta(hours=1), end=now + timedelta(hours=1)))
    assert rows[0][0] == "created_at"
    assert "provider" in rows[0]
    assert "cost_usd" in rows[0]
    assert len(rows) == 2  # header + one data row
    data = rows[1]
    assert "claude" in data
    assert "0.0123" in data or "0.012300" in data
