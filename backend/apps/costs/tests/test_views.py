from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.http import StreamingHttpResponse
from django.test import Client

from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread


@pytest.fixture
def seed_run(db):
    t = Thread.objects.create(kind="chat", title="T")
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="done")
    AIRun.objects.create(
        message=m, provider="claude", model="claude-sonnet-4-6",
        cost_usd=Decimal("0.0500"), input_tokens=100, output_tokens=10, cached_tokens=0,
        latency_ms=200, status="done",
    )
    return t


def test_summary_endpoint(client: Client, seed_run) -> None:
    now = datetime.now(tz=UTC)
    resp = client.get(f"/api/costs/summary?from={(now - timedelta(days=1)).isoformat()}&to={(now + timedelta(hours=1)).isoformat()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == "0.0500"
    assert any(p["provider"] == "claude" for p in body["by_provider"])
    assert len(body["daily"]) >= 1


def test_summary_defaults_to_30_days(client: Client, seed_run) -> None:
    resp = client.get("/api/costs/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert len(body["daily"]) == 31  # 30 days ago .. today inclusive


def test_caps_endpoint(client: Client, db) -> None:
    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("10.00"))
    resp = client.get("/api/costs/caps")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["provider"] == "claude"
    assert body[0]["daily"]["cap"] == "10.00"


def test_csv_export(client: Client, seed_run) -> None:
    now = datetime.now(tz=UTC)
    resp = client.get(f"/api/costs/export.csv?from={(now - timedelta(hours=1)).isoformat()}&to={(now + timedelta(hours=1)).isoformat()}")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/csv")
    streaming = cast(StreamingHttpResponse, resp)
    body = b"".join(streaming.streaming_content).decode()  # type: ignore[arg-type]
    assert "created_at,provider,model" in body.splitlines()[0]
    assert "claude" in body


def test_snapshot_breakdown_endpoint(client: Client, db) -> None:
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotSection

    prof = TradingProfile.objects.create(name="t")  # Snapshot requires a profile FK
    snap = Snapshot.objects.create(profile=prof)
    SnapshotSection.objects.create(snapshot=snap, kind="quotes", payload={}, status="done", payload_tokens=100)
    resp = client.get(f"/api/costs/snapshot/{snap.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["section"] == "quotes"
    assert body[0]["payload_tokens"] == 100
