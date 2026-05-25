"""Seed ladder — each rung produces the documented objects.

Each rung is idempotent and calls its prerequisite. ``analytics`` brings
everything below it.

These tests write to the **live** Postgres (the same DB the web container
serves the API from), via the ``_unblock_live_db_for_e2e`` autouse fixture
in the top-level conftest. They don't truncate at end-of-test — the seeds
are idempotent, so rerunning the suite leaves the DB in the same shape.
"""

from __future__ import annotations


def test_seed_minimal_creates_three_providers_and_two_profiles() -> None:
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig

    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()

    assert ProviderConfig.objects.filter(provider__in=["claude", "openai", "local"]).count() == 3
    assert TradingProfile.objects.filter(name__in=["E2E Default", "E2E Tools-Enabled"]).count() == 2

    tools_profile = TradingProfile.objects.get(name="E2E Tools-Enabled")
    assert tools_profile.enable_tools is True
    assert tools_profile.enable_thinking is True
    assert tools_profile.enable_memory is True
    assert tools_profile.thinking_budget == 2048


def test_seed_minimal_is_idempotent() -> None:
    from apps.secrets.models import ProviderConfig

    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()
    seed_minimal()

    assert ProviderConfig.objects.filter(provider="claude").count() == 1


def test_seed_market_creates_watchlists_and_ohlc() -> None:
    from apps.market.models import NewsItem, OHLCBar, OptionChainSnapshot
    from apps.profiles.models import Watchlist

    from e2e.fixtures.seed_market import seed_market

    seed_market()

    assert Watchlist.objects.filter(name__startswith="E2E").count() == 3
    for sym in ("AAPL", "MSFT", "SPY", "VIX"):
        assert OHLCBar.objects.filter(ticker=sym).count() > 100
    assert NewsItem.objects.count() >= 10
    assert OptionChainSnapshot.objects.filter(ticker="AAPL").count() == 14
    # Unusual-options signal must be present on the most recent chain.
    chain = OptionChainSnapshot.objects.filter(ticker="AAPL").order_by("-fetched_at").first()
    lines = chain.payload["lines"]
    assert any(ln.get("volume", 0) / max(ln.get("oi", 1), 1) >= 3.0 for ln in lines), (
        "expected an unusual-options line"
    )


def test_seed_snapshots_states() -> None:
    from apps.snapshots.models import Snapshot

    from e2e.fixtures.seed_snapshots import seed_snapshots

    seed_snapshots()

    assert Snapshot.objects.filter(status="ready").count() >= 4  # 3 ready + 1 partial-as-ready
    assert Snapshot.objects.filter(status="failed").count() >= 1

    # Every fully-ready snapshot has 7 sections with stamped tokens.
    ready_snap = Snapshot.objects.filter(objective__startswith="e2e ready").first()
    assert ready_snap.sections.count() == 7
    for section in ready_snap.sections.all():
        assert section.payload_tokens > 0


def test_seed_threads_creates_documented_set() -> None:
    from apps.threads.models import Message, Thread

    from e2e.fixtures.seed_threads import seed_threads

    seed_threads()

    assert Thread.objects.filter(title__startswith="E2E").count() >= 5
    pinned = Thread.objects.filter(title="E2E pinned thread").first()
    assert pinned is not None and pinned.pinned_snapshot_id is not None

    first = Message.objects.filter(thread=pinned, role="user").order_by("created_at").first()
    assert first is not None and first.snapshot_ref_id is not None

    compare = Thread.objects.get(title="E2E compare thread")
    branches = Message.objects.filter(
        thread=compare, role="assistant", parent_message__isnull=False
    )
    assert branches.count() == 2


def test_seed_observer_creates_schedules_and_mixed_thread() -> None:
    from apps.observer.models import ObserverSchedule
    from apps.threads.models import Message

    from e2e.fixtures.seed_observer import seed_observer

    seed_observer()

    assert ObserverSchedule.objects.filter(enabled=True).count() >= 3
    assert ObserverSchedule.objects.filter(enabled=False).count() >= 1
    assert ObserverSchedule.objects.filter(structured=True).count() >= 1
    assert ObserverSchedule.objects.filter(mode="diff").count() >= 1

    obs_msgs = Message.objects.filter(thread__title="E2E observer thread")
    assert obs_msgs.filter(role="assistant", status="done").count() >= 2
    assert obs_msgs.filter(status="failed").count() >= 1
    assert obs_msgs.filter(role="system").count() >= 1


def test_seed_triggers_creates_three_with_firings() -> None:
    from apps.triggers.models import EventTrigger, TriggerFiring

    from e2e.fixtures.seed_triggers import seed_triggers

    seed_triggers()

    assert EventTrigger.objects.filter(name__startswith="E2E").count() == 3
    simple = EventTrigger.objects.get(name="E2E always fires")
    assert TriggerFiring.objects.filter(trigger=simple).count() == 5


def test_seed_analytics_creates_airuns_across_providers() -> None:
    from apps.threads.models import AIRun

    from e2e.fixtures.seed_analytics import seed_analytics

    seed_analytics()

    runs = AIRun.objects.filter(message__thread__title="E2E plain thread")
    assert runs.count() >= 20
    assert runs.values("provider").distinct().count() == 3


def test_analytics_fixture_brings_all_rungs(analytics) -> None:
    from apps.market.models import OHLCBar
    from apps.observer.models import ObserverSchedule
    from apps.profiles.models import TradingProfile, Watchlist
    from apps.snapshots.models import Snapshot
    from apps.threads.models import AIRun, Thread
    from apps.triggers.models import EventTrigger

    assert TradingProfile.objects.count() >= 2
    assert Watchlist.objects.filter(name__startswith="E2E").count() == 3
    assert OHLCBar.objects.count() > 0
    assert Snapshot.objects.count() >= 5
    assert Thread.objects.filter(title__startswith="E2E").count() >= 5
    assert ObserverSchedule.objects.count() >= 4
    assert EventTrigger.objects.count() >= 3
    assert AIRun.objects.count() >= 20
