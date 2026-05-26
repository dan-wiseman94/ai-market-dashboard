"""Provider leaderboard groups AIRuns by provider+model and reports
- runs, total_cost_usd, avg_latency_ms
- avg_forward_return_pct (for runs attached to a snapshot we can price)
- coverage_pct
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.analytics.services.leaderboard import provider_leaderboard
from apps.market.models import OHLCBar
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import AIRun, Message, Thread


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="p", style="s")


def _mk_run(
    *,
    provider: str,
    model: str,
    cost: str,
    latency_ms: int,
    created_at: datetime,
    snap_ticker: str | None,
    profile,
) -> AIRun:
    snap = None
    if snap_ticker is not None:
        snap = Snapshot.objects.create(profile=profile, status="ready", source="manual")
        SnapshotSection.objects.create(
            snapshot=snap,
            kind="quotes",
            status="done",
            payload={snap_ticker: {"last": 100.0}},
        )
    thread = Thread.objects.create(kind="consult", profile=profile, pinned_snapshot=snap)
    msg = Message.objects.create(
        thread=thread,
        role="assistant",
        content={"text": ""},
        status="done",
    )
    run = AIRun.objects.create(
        message=msg,
        provider=provider,
        model=model,
        cost_usd=Decimal(cost),
        latency_ms=latency_ms,
        status="done",
    )
    AIRun.objects.filter(id=run.id).update(created_at=_aware(created_at))
    if snap is not None:
        Snapshot.objects.filter(id=snap.id).update(captured_at=_aware(created_at))
    return run


def _mk_bar(ticker: str, ts: datetime, close: float) -> None:
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1h",
        ts=_aware(ts),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def test_leaderboard_groups_by_provider_model(db, profile) -> None:
    now = datetime(2026, 4, 10, 14, 30)
    _mk_run(
        provider="claude",
        model="claude-opus-4-7",
        cost="0.10",
        latency_ms=1500,
        created_at=now,
        snap_ticker=None,
        profile=profile,
    )
    _mk_run(
        provider="claude",
        model="claude-opus-4-7",
        cost="0.20",
        latency_ms=2500,
        created_at=now,
        snap_ticker=None,
        profile=profile,
    )
    _mk_run(
        provider="openai",
        model="gpt-5",
        cost="0.05",
        latency_ms=800,
        created_at=now,
        snap_ticker=None,
        profile=profile,
    )

    rows = provider_leaderboard(
        start=_aware(now - timedelta(days=1)),
        end=_aware(now + timedelta(days=1)),
        forward_hours=24,
    )
    by_key = {(r["provider"], r["model"]): r for r in rows}
    claude = by_key[("claude", "claude-opus-4-7")]
    openai = by_key[("openai", "gpt-5")]
    assert claude["runs"] == 2
    assert claude["total_cost_usd"] == Decimal("0.30")
    assert claude["avg_latency_ms"] == 2000
    assert openai["runs"] == 1


def test_leaderboard_computes_forward_return_pct(db, profile) -> None:
    # Wed 2026-04-15 20:00 UTC = NYSE close; +1 trading session = Thu 2026-04-16 close.
    # Bars must sit at the actual session closes so the 12h tolerance window finds them.
    now = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    _mk_run(
        provider="claude",
        model="claude-opus-4-7",
        cost="0.10",
        latency_ms=1000,
        created_at=now,
        snap_ticker="AAPL",
        profile=profile,
    )
    _mk_bar("AAPL", now, 100.0)
    _mk_bar("AAPL", datetime(2026, 4, 16, 20, 0, tzinfo=UTC), 110.0)

    rows = provider_leaderboard(
        start=now - timedelta(days=1),
        end=now + timedelta(days=1),
        forward_hours=24,
    )
    r = next(r for r in rows if r["provider"] == "claude")
    assert r["avg_forward_return_pct"] == pytest.approx(10.0, rel=0.01)
    assert r["coverage_pct"] == pytest.approx(100.0)


def test_leaderboard_coverage_when_no_price_history(db, profile) -> None:
    now = datetime(2026, 4, 10, 14, 30)
    _mk_run(
        provider="claude",
        model="claude-opus-4-7",
        cost="0.10",
        latency_ms=1000,
        created_at=now,
        snap_ticker="ZZZZ",
        profile=profile,
    )
    rows = provider_leaderboard(
        start=_aware(now - timedelta(days=1)),
        end=_aware(now + timedelta(days=1)),
        forward_hours=24,
    )
    r = next(r for r in rows if r["provider"] == "claude")
    assert r["runs"] == 1
    assert r["coverage_pct"] == 0.0
    assert r["avg_forward_return_pct"] is None


def test_leaderboard_filters_by_window(db, profile) -> None:
    now = datetime(2026, 4, 10, 14, 30)
    _mk_run(
        provider="claude",
        model="claude-opus-4-7",
        cost="0.10",
        latency_ms=1000,
        created_at=now - timedelta(days=60),
        snap_ticker=None,
        profile=profile,
    )
    rows = provider_leaderboard(
        start=_aware(now - timedelta(days=1)),
        end=_aware(now + timedelta(days=1)),
        forward_hours=24,
    )
    assert rows == []
