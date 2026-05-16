# E2E Phase 1 — Seed Ladder + Scenario Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 7-rung seed ladder and the scenario-engine dispatch layer so downstream phases have a rich deterministic world and can switch mock behavior via HTTP header.

**Architecture:** Seed rungs are idempotent functions in `e2e/fixtures/`, each calling the prior rung. The scenario engine lives in `apps/core/mocks/` as a Django middleware + ContextVar + per-service handler registry, guarded by `MOCK_EXTERNAL=true`.

**Tech Stack:** Django middleware + ContextVar, pytest-django, factory helpers. No new pip deps.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §3 (seed ladder), §7 (scenario engine).

**Prerequisite:** Phase 0 complete.

---

## File structure

**Create:**
- `e2e/fixtures/seed_market.py`, `seed_snapshots.py`, `seed_threads.py`, `seed_observer.py`, `seed_triggers.py`, `seed_analytics.py`
- `apps/core/mocks/__init__.py` (replaces `apps/core/mocks.py`)
- `apps/core/mocks/scenarios.py`
- `apps/core/mocks/middleware.py`
- `apps/core/mocks/providers.py` (moves current claude/openai/schwab mock fns here)
- `e2e/mocks/client.py` (implementation, not placeholder)
- `e2e/api/test_scenario_engine_disabled_in_prod.py`
- `e2e/tests/test_seed_ladder.py`
- `e2e/tests/test_scenario_engine.py`

**Modify:**
- `e2e/fixtures/seed_minimal.py` — extend to 3 providers + 2 profiles
- `e2e/conftest.py` — add 7 rung fixtures + scenario_client fixture
- `backend/config/settings/base.py` — conditionally insert `ScenarioHeaderMiddleware` when `MOCK_EXTERNAL`
- `backend/apps/ai/providers/claude.py` — read `current_scenario()` on mock path
- `backend/apps/ai/providers/openai.py` — same
- `backend/apps/ai/providers/local.py` — same
- `backend/apps/market/clients/schwab.py` — same
- `backend/apps/market/clients/finnhub.py` — same
- `backend/apps/files/client.py` — same

**Delete:**
- `apps/core/mocks.py` (replaced by package)

---

## Task 1 — Extend `seed_minimal`

**Files:**
- Modify: `e2e/fixtures/seed_minimal.py`
- Create: `e2e/tests/test_seed_ladder.py`

- [ ] **Step 1: Write failing test**

Create `e2e/tests/test_seed_ladder.py`:

```python
"""Seed ladder — asserts each rung produces the documented objects."""
from __future__ import annotations

import pytest


@pytest.mark.django_db
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


@pytest.mark.django_db
def test_seed_minimal_is_idempotent() -> None:
    from apps.secrets.models import ProviderConfig
    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()
    seed_minimal()

    assert ProviderConfig.objects.filter(provider="claude").count() == 1
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py::test_seed_minimal_creates_three_providers_and_two_profiles -v`
Expected: FAIL — likely only 1 provider, 1 profile.

- [ ] **Step 3: Update `e2e/fixtures/seed_minimal.py`**

```python
"""Rung 1 — providers + profiles."""
from __future__ import annotations

from decimal import Decimal


def seed_minimal() -> None:
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig

    for provider, model in (
        ("claude", "claude-sonnet-4-6"),
        ("openai", "gpt-5-mini"),
        ("local", "local-7b"),
    ):
        ProviderConfig.objects.update_or_create(
            provider=provider,
            defaults={
                "base_url": "" if provider != "local" else "http://localhost:11434/v1",
                "default_model": model,
                "enabled": True,
                "daily_cost_cap_usd": Decimal("100.00"),
                "monthly_cost_cap_usd": Decimal("1000.00"),
            },
        )

    TradingProfile.objects.update_or_create(
        name="E2E Default",
        defaults={
            "style": "E2E test profile — observational trading style.",
            "default_provider": "claude",
            "default_model": "claude-sonnet-4-6",
            "active": True,
        },
    )
    TradingProfile.objects.update_or_create(
        name="E2E Tools-Enabled",
        defaults={
            "style": "E2E profile with tools + thinking + memory enabled.",
            "default_provider": "claude",
            "default_model": "claude-sonnet-4-6",
            "enable_tools": True,
            "enable_thinking": True,
            "thinking_budget": 2048,
            "enable_memory": True,
            "active": False,
        },
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_minimal.py e2e/tests/test_seed_ladder.py
git commit -m "$(cat <<'EOF'
feat(e2e): extend seed_minimal — 3 providers + tools-enabled profile

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — `seed_market`

**Files:**
- Create: `e2e/fixtures/seed_market.py`

- [ ] **Step 1: Write failing test**

Append to `e2e/tests/test_seed_ladder.py`:

```python
@pytest.mark.django_db
def test_seed_market_creates_watchlists_and_ohlc() -> None:
    from apps.market.models import NewsItem, OHLCBar, OptionChainSnapshot, Position, Watchlist
    from e2e.fixtures.seed_market import seed_market

    seed_market()

    assert Watchlist.objects.filter(name__startswith="E2E").count() == 3
    # 30 days × 4 tickers × ~6.5 hours/trading-day bars each — at least 3 per ticker
    for sym in ("AAPL", "MSFT", "SPY", "VIX"):
        assert OHLCBar.objects.filter(ticker=sym).count() > 100
    assert Position.objects.count() >= 5
    assert NewsItem.objects.count() >= 10
    assert OptionChainSnapshot.objects.filter(ticker="AAPL").count() >= 14
    # Unusual-options signal must be present
    chain = OptionChainSnapshot.objects.filter(ticker="AAPL").last()
    assert any(line.get("volume", 0) / max(line.get("oi", 1), 1) >= 3.0 for line in chain.lines)
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py::test_seed_market_creates_watchlists_and_ohlc -v`
Expected: FAIL — `ModuleNotFoundError: e2e.fixtures.seed_market`.

- [ ] **Step 3: Create `e2e/fixtures/seed_market.py`**

```python
"""Rung 2 — market data: watchlists, OHLC, positions, news, option chains."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def seed_market() -> None:
    from e2e.fixtures.seed_minimal import seed_minimal
    seed_minimal()

    from apps.market.models import NewsItem, OHLCBar, OptionChainSnapshot, Position, Watchlist

    tickers = ("AAPL", "MSFT", "SPY", "VIX", "NVDA", "AMD", "GOOGL", "TSLA")
    for name, syms in (
        ("E2E Core", ["AAPL", "MSFT", "SPY"]),
        ("E2E Tech", ["NVDA", "AMD", "GOOGL", "TSLA"]),
        ("E2E Empty", []),
    ):
        wl, _ = Watchlist.objects.update_or_create(name=name, defaults={"tickers": syms})

    rng = random.Random(42)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for sym in ("AAPL", "MSFT", "SPY", "VIX"):
        base = {"AAPL": 175.0, "MSFT": 420.0, "SPY": 500.0, "VIX": 15.0}[sym]
        for day in range(30):
            for hour in range(7):  # 9:30–16:00 ET roughly
                ts = now - timedelta(days=day, hours=hour)
                drift = rng.uniform(-0.02, 0.02)
                o = base * (1 + drift)
                h = o * 1.002
                l = o * 0.998
                c = o * (1 + rng.uniform(-0.005, 0.005))
                OHLCBar.objects.update_or_create(
                    ticker=sym, timeframe="1h", ts=ts,
                    defaults={"open": o, "high": h, "low": l, "close": c, "volume": rng.randint(1_000_000, 10_000_000)},
                )

    for sym, qty, px in (("AAPL", 100, 150.0), ("MSFT", 50, 380.0), ("NVDA", 30, 450.0),
                         ("SPY", 10, 480.0), ("GOOGL", 20, 140.0)):
        Position.objects.update_or_create(ticker=sym, defaults={"qty": qty, "avg_price": px})

    for i in range(10):
        NewsItem.objects.update_or_create(
            source_url=f"https://example.test/news/{i}",
            defaults={
                "title": f"E2E news headline {i}",
                "summary": "E2E fixture summary.",
                "published_at": now - timedelta(hours=i * 3),
                "tickers": ["AAPL"] if i % 2 == 0 else ["MSFT"],
            },
        )

    # 14 days of AAPL option-chain snapshots
    base_iv = 0.28
    for day in range(14):
        ts = now - timedelta(days=day)
        iv = base_iv + rng.uniform(-0.02, 0.02)
        lines = [
            {"strike": 170, "type": "call", "iv": iv, "volume": 1000, "oi": 500},
            {"strike": 180, "type": "put", "iv": iv + 0.01, "volume": 800, "oi": 600},
        ]
        if day == 0:
            # Unusual-options trigger — volume/oi >= 3.0 and iv_z >= 1.5
            lines.append({"strike": 175, "type": "call", "iv": base_iv + 0.10, "volume": 4000, "oi": 1000})
        OptionChainSnapshot.objects.update_or_create(
            ticker="AAPL", fetched_at=ts,
            defaults={"lines": lines},
        )
```

*(Adjust model field names if they differ — inspect `apps/market/models.py` before running. If `Watchlist.tickers` is a relation not a JSONField, swap to the appropriate call.)*

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py::test_seed_market_creates_watchlists_and_ohlc -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_market.py e2e/tests/test_seed_ladder.py
git commit -m "$(cat <<'EOF'
feat(e2e): seed_market rung — watchlists + OHLC + positions + chain

Deterministic seed (rng seed 42) across 30 days × 4 tickers with one
unusual-options line to trip analytics detectors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — `seed_snapshots`

**Files:**
- Create: `e2e/fixtures/seed_snapshots.py`

- [ ] **Step 1: Write failing test**

Append to `e2e/tests/test_seed_ladder.py`:

```python
@pytest.mark.django_db
def test_seed_snapshots_creates_three_ready_one_partial_one_failed() -> None:
    from apps.snapshots.models import Snapshot
    from e2e.fixtures.seed_snapshots import seed_snapshots

    seed_snapshots()

    assert Snapshot.objects.filter(status="ready").count() >= 3
    assert Snapshot.objects.filter(status="partial").count() >= 1
    assert Snapshot.objects.filter(status="failed").count() >= 1

    # Ready snapshots have all 7 sections with payload_tokens stamped
    snap = Snapshot.objects.filter(status="ready").first()
    assert snap.sections.count() == 7
    for section in snap.sections.all():
        assert section.payload_tokens > 0
```

- [ ] **Step 2: Run to verify fail**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py::test_seed_snapshots_creates_three_ready_one_partial_one_failed -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `e2e/fixtures/seed_snapshots.py`**

```python
"""Rung 3 — snapshots in ready/partial/failed states."""
from __future__ import annotations

from datetime import datetime, timezone


SECTION_NAMES = ("quotes", "ohlc", "chain", "positions", "breadth", "news", "charts")


def seed_snapshots() -> None:
    from e2e.fixtures.seed_market import seed_market
    seed_market()

    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotSection

    profile = TradingProfile.objects.get(name="E2E Default")
    now = datetime.now(timezone.utc)

    for idx in range(3):
        snap, _ = Snapshot.objects.update_or_create(
            profile=profile, objective=f"e2e ready snap {idx}",
            defaults={"status": "ready", "created_at": now},
        )
        for name in SECTION_NAMES:
            SnapshotSection.objects.update_or_create(
                snapshot=snap, name=name,
                defaults={"status": "ready", "payload": {"mock": name}, "payload_tokens": 128},
            )

    # Partial — news section failed
    partial, _ = Snapshot.objects.update_or_create(
        profile=profile, objective="e2e partial snap",
        defaults={"status": "partial", "created_at": now},
    )
    for name in SECTION_NAMES:
        SnapshotSection.objects.update_or_create(
            snapshot=partial, name=name,
            defaults={"status": "failed" if name == "news" else "ready",
                      "payload": {} if name == "news" else {"mock": name},
                      "payload_tokens": 0 if name == "news" else 128},
        )

    # Failed — no sections populated
    Snapshot.objects.update_or_create(
        profile=profile, objective="e2e failed snap",
        defaults={"status": "failed", "created_at": now},
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py::test_seed_snapshots_creates_three_ready_one_partial_one_failed -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_snapshots.py e2e/tests/test_seed_ladder.py
git commit -m "$(cat <<'EOF'
feat(e2e): seed_snapshots rung — 3 ready + 1 partial + 1 failed

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — `seed_threads`

**Files:**
- Create: `e2e/fixtures/seed_threads.py`

- [ ] **Step 1: Write failing test**

Append to `e2e/tests/test_seed_ladder.py`:

```python
@pytest.mark.django_db
def test_seed_threads_creates_documented_set() -> None:
    from apps.threads.models import Thread, Message
    from e2e.fixtures.seed_threads import seed_threads

    seed_threads()

    assert Thread.objects.count() >= 5
    pinned = Thread.objects.filter(pinned_snapshot__isnull=False)
    assert pinned.exists()
    # Pinned thread has the synthetic first user message
    first = Message.objects.filter(thread=pinned.first(), role="user").order_by("created_at").first()
    assert first is not None and first.snapshot_ref_id is not None

    # Compare thread: one parent message with 2 branches
    compare_thread = Thread.objects.get(title__startswith="E2E compare")
    branches = Message.objects.filter(thread=compare_thread, role="assistant", parent_id__isnull=False)
    assert branches.count() == 2
```

- [ ] **Step 2: Run to verify fail** — module not found.

- [ ] **Step 3: Create `e2e/fixtures/seed_threads.py`**

```python
"""Rung 4 — threads with varied histories."""
from __future__ import annotations

from django.db import transaction


def seed_threads() -> None:
    from e2e.fixtures.seed_snapshots import seed_snapshots
    seed_snapshots()

    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot
    from apps.threads.models import Thread, Message
    from apps.threads.services import serialize_for_ai

    profile = TradingProfile.objects.get(name="E2E Default")
    snap = Snapshot.objects.filter(status="ready").first()

    # 1. Pinned thread
    with transaction.atomic():
        pinned, _ = Thread.objects.get_or_create(
            title="E2E pinned thread",
            defaults={"profile": profile, "pinned_snapshot": snap},
        )
        if not pinned.messages.exists():
            Message.objects.create(
                thread=pinned, role="user", status="done",
                content={"text": serialize_for_ai(snap)}, snapshot_ref=snap,
            )

    # 2. Plain thread
    Thread.objects.get_or_create(title="E2E plain thread", defaults={"profile": profile})

    # 3. Compare thread (2 branches)
    with transaction.atomic():
        compare, _ = Thread.objects.get_or_create(title="E2E compare thread", defaults={"profile": profile})
        if not compare.messages.filter(parent_id__isnull=False).exists():
            parent = Message.objects.create(thread=compare, role="user", status="done",
                                            content={"text": "compare these"})
            for branch_n, provider in enumerate(("claude", "openai"), start=1):
                Message.objects.create(
                    thread=compare, role="assistant", status="done",
                    parent=parent,
                    content={"text": f"Branch {branch_n} from {provider}"},
                )

    # 4. Tool-use thread
    with transaction.atomic():
        tools, _ = Thread.objects.get_or_create(title="E2E tool-use thread", defaults={"profile": profile})
        if not tools.messages.exists():
            u = Message.objects.create(thread=tools, role="user", status="done",
                                       content={"text": "use a tool"})
            Message.objects.create(thread=tools, role="assistant", status="done",
                                   content={"blocks": [
                                       {"type": "tool_use", "name": "quotes_now", "input": {"ticker": "AAPL"}},
                                       {"type": "tool_result", "content": {"last": 175.0}},
                                       {"type": "text", "text": "Result: 175"},
                                   ]})

    # 5. Empty ready-to-send
    Thread.objects.get_or_create(title="E2E empty thread", defaults={"profile": profile})
```

- [ ] **Step 4: Run to verify pass.**

Run: `docker compose exec web pytest e2e/tests/test_seed_ladder.py::test_seed_threads_creates_documented_set -v`

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_threads.py e2e/tests/test_seed_ladder.py
git commit -m "feat(e2e): seed_threads rung — 5 threads across variants

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5 — `seed_observer`

**Files:**
- Create: `e2e/fixtures/seed_observer.py`

- [ ] **Step 1: Test**

Append to `e2e/tests/test_seed_ladder.py`:

```python
@pytest.mark.django_db
def test_seed_observer() -> None:
    from apps.observer.models import ObserverSchedule
    from apps.threads.models import Message
    from e2e.fixtures.seed_observer import seed_observer

    seed_observer()
    assert ObserverSchedule.objects.filter(active=True).count() >= 1
    assert ObserverSchedule.objects.filter(active=False).count() >= 1
    assert ObserverSchedule.objects.filter(structured=True).count() >= 1
    assert ObserverSchedule.objects.filter(mode="diff").count() >= 1
    # Observer thread with mixed outcomes
    obs_msgs = Message.objects.filter(thread__title__icontains="observer")
    assert obs_msgs.filter(role="assistant", status="done").count() >= 2
    assert obs_msgs.filter(status="failed").count() >= 1
    assert obs_msgs.filter(role="system").count() >= 1
```

- [ ] **Step 2: Run fail.**

- [ ] **Step 3: Create `e2e/fixtures/seed_observer.py`**

```python
"""Rung 5 — observer schedules + an observer thread with mixed outcomes."""
from __future__ import annotations

from datetime import datetime, timezone


def seed_observer() -> None:
    from e2e.fixtures.seed_threads import seed_threads
    seed_threads()

    from apps.observer.models import ObserverSchedule
    from apps.observer.services.schedule_sync import sync_periodic_task
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread, Message

    profile = TradingProfile.objects.get(name="E2E Default")
    now = datetime.now(timezone.utc)

    s1, _ = ObserverSchedule.objects.update_or_create(
        name="E2E active schedule",
        defaults={"profile": profile, "interval_seconds": 60, "active": True, "mode": "full"},
    )
    sync_periodic_task(s1)
    s2, _ = ObserverSchedule.objects.update_or_create(
        name="E2E paused schedule",
        defaults={"profile": profile, "interval_seconds": 60, "active": False, "mode": "full"},
    )
    sync_periodic_task(s2)
    s3, _ = ObserverSchedule.objects.update_or_create(
        name="E2E structured schedule",
        defaults={"profile": profile, "interval_seconds": 60, "active": True, "mode": "full", "structured": True},
    )
    sync_periodic_task(s3)
    s4, _ = ObserverSchedule.objects.update_or_create(
        name="E2E diff schedule",
        defaults={"profile": profile, "interval_seconds": 60, "active": True, "mode": "diff"},
    )
    sync_periodic_task(s4)

    obs_thread, _ = Thread.objects.get_or_create(
        title="E2E observer thread", defaults={"profile": profile, "observer_schedule": s1},
    )
    if not obs_thread.messages.exists():
        for i in range(2):
            Message.objects.create(thread=obs_thread, role="assistant", status="done",
                                   content={"text": f"observation {i}"}, created_at=now)
        Message.objects.create(thread=obs_thread, role="assistant", status="failed",
                               content={"error": "mock failure"}, created_at=now)
        Message.objects.create(thread=obs_thread, role="system", status="done",
                               content={"text": "skipped: cost cap exceeded"}, created_at=now)
```

*(If `ObserverSchedule` doesn't have `mode` or `structured`, check the real model; adjust field names before running.)*

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_observer.py e2e/tests/test_seed_ladder.py
git commit -m "feat(e2e): seed_observer rung — 4 schedules + observer thread

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 — `seed_triggers`

**Files:**
- Create: `e2e/fixtures/seed_triggers.py`

- [ ] **Step 1: Test**

```python
@pytest.mark.django_db
def test_seed_triggers() -> None:
    from apps.triggers.models import Trigger, TriggerFiring
    from e2e.fixtures.seed_triggers import seed_triggers
    seed_triggers()

    assert Trigger.objects.count() >= 3
    trig_with_firings = Trigger.objects.annotate_firings().filter(firing_count__gt=0).first()
    assert TriggerFiring.objects.filter(trigger=trig_with_firings).count() == 5
```

*(If no `annotate_firings` manager exists, swap for `Trigger.objects.get(name="always fires")` and count firings.)*

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Create `e2e/fixtures/seed_triggers.py`**

```python
"""Rung 6 — triggers + firings."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def seed_triggers() -> None:
    from e2e.fixtures.seed_observer import seed_observer
    seed_observer()

    from apps.triggers.models import Trigger, TriggerFiring

    simple, _ = Trigger.objects.update_or_create(
        name="E2E always fires",
        defaults={
            "condition": {"ticker": "AAPL", "metric": "last", "op": ">", "value": 0},
            "active": True,
        },
    )
    Trigger.objects.update_or_create(
        name="E2E pct_change",
        defaults={
            "condition": {"ticker": "AAPL", "metric": "pct_change", "op": ">", "value": 5, "window": "1h"},
            "active": True,
        },
    )
    Trigger.objects.update_or_create(
        name="E2E complex DSL",
        defaults={
            "condition": {"all": [
                {"ticker": "AAPL", "metric": "last", "op": ">", "value": 170},
                {"any": [
                    {"ticker": "MSFT", "metric": "pct_change", "op": ">", "value": 1, "window": "1h"},
                    {"not": {"ticker": "VIX", "metric": "last", "op": ">", "value": 20}},
                ]},
            ]},
            "active": True,
        },
    )

    now = datetime.now(timezone.utc)
    for day in range(3):
        for fire in range(5 if day == 0 else 0):
            TriggerFiring.objects.create(
                trigger=simple,
                fired_at=now - timedelta(days=day, minutes=fire * 15),
                context={"last": 175.0 + fire},
            )
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_triggers.py e2e/tests/test_seed_ladder.py
git commit -m "feat(e2e): seed_triggers rung — 3 triggers + 5 firings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7 — `seed_analytics`

**Files:**
- Create: `e2e/fixtures/seed_analytics.py`

- [ ] **Step 1: Test**

```python
@pytest.mark.django_db
def test_seed_analytics() -> None:
    from apps.ai.models import AIRun
    from e2e.fixtures.seed_analytics import seed_analytics

    seed_analytics()
    assert AIRun.objects.count() >= 20
    # 3 providers represented
    assert AIRun.objects.values("provider").distinct().count() >= 3
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Create `e2e/fixtures/seed_analytics.py`**

```python
"""Rung 7 — AI runs across providers + forward-return correlation data."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def seed_analytics() -> None:
    from e2e.fixtures.seed_triggers import seed_triggers
    seed_triggers()

    from apps.ai.models import AIRun
    from apps.snapshots.models import Snapshot
    from apps.triggers.models import Trigger, TriggerFiring

    rng = random.Random(7)
    now = datetime.now(timezone.utc)
    providers = ("claude", "openai", "local")
    models = {"claude": "claude-sonnet-4-6", "openai": "gpt-5-mini", "local": "local-7b"}

    ready_snaps = list(Snapshot.objects.filter(status="ready"))
    for i in range(20):
        prov = providers[i % 3]
        snap = ready_snaps[i % max(len(ready_snaps), 1)] if ready_snaps else None
        AIRun.objects.create(
            provider=prov,
            model=models[prov],
            snapshot=snap,
            cost_usd=Decimal(str(round(rng.uniform(0.001, 0.25), 4))),
            duration_ms=rng.randint(300, 15_000),
            created_at=now - timedelta(days=i % 7, hours=rng.randint(0, 23)),
            prompt_tokens=rng.randint(500, 8_000),
            completion_tokens=rng.randint(100, 2_000),
        )

    # 15 extra firings across the heatmap grid
    trig = Trigger.objects.filter(name="E2E always fires").first()
    if trig is not None:
        for i in range(15):
            TriggerFiring.objects.create(
                trigger=trig,
                fired_at=now - timedelta(days=i % 7, hours=i),
                context={"last": 175.0},
            )
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add e2e/fixtures/seed_analytics.py e2e/tests/test_seed_ladder.py
git commit -m "feat(e2e): seed_analytics rung — 20 AIRuns + 15 heatmap firings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8 — Expose rungs as pytest fixtures

**Files:**
- Modify: `e2e/conftest.py`

- [ ] **Step 1: Write fixture-wire test**

Append to `e2e/tests/test_seed_ladder.py`:

```python
@pytest.mark.django_db(transaction=True)
def test_analytics_fixture_brings_all_rungs(analytics) -> None:
    from apps.ai.models import AIRun
    from apps.profiles.models import TradingProfile
    from apps.market.models import Watchlist
    from apps.snapshots.models import Snapshot
    from apps.threads.models import Thread
    from apps.observer.models import ObserverSchedule
    from apps.triggers.models import Trigger

    assert TradingProfile.objects.count() >= 2
    assert Watchlist.objects.count() >= 3
    assert Snapshot.objects.count() >= 5
    assert Thread.objects.count() >= 5
    assert ObserverSchedule.objects.count() >= 4
    assert Trigger.objects.count() >= 3
    assert AIRun.objects.count() >= 20
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Append fixtures to `e2e/conftest.py`**

```python
@pytest.fixture
def minimal(db):
    from e2e.fixtures.seed_minimal import seed_minimal
    seed_minimal()


@pytest.fixture
def market(minimal):
    from e2e.fixtures.seed_market import seed_market
    seed_market()


@pytest.fixture
def snapshots(market):
    from e2e.fixtures.seed_snapshots import seed_snapshots
    seed_snapshots()


@pytest.fixture
def threads(snapshots):
    from e2e.fixtures.seed_threads import seed_threads
    seed_threads()


@pytest.fixture
def observer(threads):
    from e2e.fixtures.seed_observer import seed_observer
    seed_observer()


@pytest.fixture
def triggers(observer):
    from e2e.fixtures.seed_triggers import seed_triggers
    seed_triggers()


@pytest.fixture
def analytics(triggers):
    from e2e.fixtures.seed_analytics import seed_analytics
    seed_analytics()
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add e2e/conftest.py e2e/tests/test_seed_ladder.py
git commit -m "feat(e2e): 7-rung seed-ladder fixtures

minimal → market → snapshots → threads → observer → triggers → analytics.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9 — Convert `apps/core/mocks.py` → package

**Files:**
- Delete: `backend/apps/core/mocks.py`
- Create: `backend/apps/core/mocks/__init__.py`, `providers.py`

- [ ] **Step 1: Write migration test**

Create `e2e/tests/test_scenario_engine.py`:

```python
"""Scenario engine — ContextVar + registry + middleware."""
from __future__ import annotations

import pytest


def test_mocks_package_importable() -> None:
    from apps.core.mocks import current_scenario, set_scenario  # noqa: F401


def test_default_scenario_is_default() -> None:
    from apps.core.mocks import current_scenario
    assert current_scenario() == "default"


def test_set_scenario_round_trip() -> None:
    from apps.core.mocks import set_scenario, current_scenario
    set_scenario("claude-5xx")
    assert current_scenario() == "claude-5xx"
    set_scenario("default")
```

- [ ] **Step 2: Run to verify fail** — module shape wrong.

- [ ] **Step 3: Move file into package**

```bash
mkdir -p backend/apps/core/mocks
git mv backend/apps/core/mocks.py backend/apps/core/mocks/providers.py
```

Create `backend/apps/core/mocks/__init__.py`:

```python
"""Mock dispatch + scenario engine — loaded only when MOCK_EXTERNAL=true."""
from __future__ import annotations

from contextvars import ContextVar

from .providers import *  # noqa: F401,F403 — back-compat re-export

_scenario: ContextVar[str] = ContextVar("e2e_scenario", default="default")


def set_scenario(name: str) -> None:
    _scenario.set(name)


def current_scenario() -> str:
    return _scenario.get()


def reset_scenario() -> None:
    _scenario.set("default")
```

- [ ] **Step 4: Pass.**

Run: `docker compose exec web pytest e2e/tests/test_scenario_engine.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/core/mocks/ e2e/tests/test_scenario_engine.py
git commit -m "refactor(mocks): mocks.py → apps/core/mocks/ package

Adds ContextVar-based scenario state (current_scenario/set_scenario/reset_scenario).
Existing mock functions re-exported from .providers for back-compat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10 — `scenarios.py` registry

**Files:**
- Create: `backend/apps/core/mocks/scenarios.py`

- [ ] **Step 1: Test**

Append to `e2e/tests/test_scenario_engine.py`:

```python
def test_registry_has_thirteen_scenarios() -> None:
    from apps.core.mocks.scenarios import SCENARIOS
    expected = {
        "default", "claude-5xx", "claude-5xx-midstream", "claude-ratelimit",
        "openai-timeout", "schwab-401", "schwab-oauth-ok", "news-503",
        "cap-exceeded", "files-upload-fail", "tool-use-loop", "thinking-heavy",
        "structured-observation",
    }
    assert set(SCENARIOS.keys()) == expected


def test_registry_default_entry_has_all_services() -> None:
    from apps.core.mocks.scenarios import SCENARIOS
    default = SCENARIOS["default"]
    for svc in ("claude", "openai", "schwab", "finnhub", "files"):
        assert svc in default
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Create registry**

Create `backend/apps/core/mocks/scenarios.py`:

```python
"""Scenario registry — maps (scenario, service) → handler name."""
from __future__ import annotations

from typing import Callable


# Registry structure: {scenario: {service: handler_name}}
# Handlers resolved to callables at dispatch time by providers.
SCENARIOS: dict[str, dict[str, str]] = {
    "default": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "schwab": "ok",
        "finnhub": "ok",
        "files": "ok",
    },
    "claude-5xx": {
        "claude": "error_503_prestream",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "claude-5xx-midstream": {
        "claude": "stream_then_500",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "claude-ratelimit": {
        "claude": "error_429_retry_after",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "openai-timeout": {
        "claude": "stream_mocked_response",
        "openai": "hang_60s",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "schwab-401": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "schwab": "error_401_token_expired", "finnhub": "ok", "files": "ok",
    },
    "schwab-oauth-ok": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "schwab": "oauth_full_flow", "finnhub": "ok", "files": "ok",
    },
    "news-503": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "error_503", "files": "ok",
    },
    "cap-exceeded": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "files-upload-fail": {
        "claude": "stream_mocked_response",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "error_500_on_upload",
    },
    "tool-use-loop": {
        "claude": "stream_tool_use_loop",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "thinking-heavy": {
        "claude": "stream_thinking_heavy",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
    "structured-observation": {
        "claude": "structured_observation_report",
        "openai": "stream_mocked_response",
        "schwab": "ok", "finnhub": "ok", "files": "ok",
    },
}


def handler_for(scenario: str, service: str) -> str:
    """Return the handler name for (scenario, service), falling back to default."""
    return SCENARIOS.get(scenario, SCENARIOS["default"]).get(
        service, SCENARIOS["default"][service]
    )
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/apps/core/mocks/scenarios.py e2e/tests/test_scenario_engine.py
git commit -m "feat(mocks): scenario registry with 13 named scenarios

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11 — `ScenarioHeaderMiddleware`

**Files:**
- Create: `backend/apps/core/mocks/middleware.py`
- Modify: `backend/config/settings/base.py`

- [ ] **Step 1: Test**

Append to `e2e/tests/test_scenario_engine.py`:

```python
@pytest.mark.integration
def test_middleware_sets_scenario_from_header(api_base_url: str) -> None:
    import httpx
    from apps.core.mocks import current_scenario

    # Use /api/core/_scenario_probe — a dev-only view we wire in Step 4.
    r = httpx.get(f"{api_base_url}/api/_scenario_probe/", headers={"X-E2E-Scenario": "claude-5xx"}, timeout=5)
    assert r.status_code == 200
    assert r.json()["scenario"] == "claude-5xx"


@pytest.mark.integration
def test_middleware_noop_without_header(api_base_url: str) -> None:
    import httpx
    r = httpx.get(f"{api_base_url}/api/_scenario_probe/", timeout=5)
    assert r.json()["scenario"] == "default"
```

- [ ] **Step 2: Fail** — `_scenario_probe/` 404.

- [ ] **Step 3: Create middleware**

Create `backend/apps/core/mocks/middleware.py`:

```python
"""ScenarioHeaderMiddleware — only loaded when MOCK_EXTERNAL=true."""
from __future__ import annotations

from django.conf import settings

from apps.core.mocks import set_scenario, reset_scenario


class ScenarioHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "MOCK_EXTERNAL", False):
            scenario = request.headers.get("X-E2E-Scenario", "default")
            set_scenario(scenario)
            try:
                return self.get_response(request)
            finally:
                reset_scenario()
        return self.get_response(request)
```

- [ ] **Step 4: Wire middleware + probe endpoint**

In `backend/config/settings/base.py`, after `MIDDLEWARE = [...]`, append:

```python
if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true"):
    MIDDLEWARE = [*MIDDLEWARE, "apps.core.mocks.middleware.ScenarioHeaderMiddleware"]
```

In `backend/apps/core/views.py`, add:

```python
from django.conf import settings
from django.http import JsonResponse


def scenario_probe(request):
    """Dev-only: echo current scenario. Only registered when MOCK_EXTERNAL."""
    from apps.core.mocks import current_scenario
    return JsonResponse({"scenario": current_scenario()})
```

In `backend/apps/core/urls.py`, conditional path:

```python
import os
from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),
]

if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true"):
    urlpatterns.append(path("_scenario_probe/", views.scenario_probe, name="scenario-probe"))
```

- [ ] **Step 5: Pass.**

Run: `docker compose -f compose.yaml -f compose.e2e.yaml up -d && docker compose exec web pytest e2e/tests/test_scenario_engine.py::test_middleware_sets_scenario_from_header -v`

- [ ] **Step 6: Commit**

```bash
git add backend/apps/core/mocks/middleware.py backend/config/settings/base.py backend/apps/core/views.py backend/apps/core/urls.py e2e/tests/test_scenario_engine.py
git commit -m "$(cat <<'EOF'
feat(mocks): ScenarioHeaderMiddleware + /_scenario_probe/

Middleware reads X-E2E-Scenario when MOCK_EXTERNAL=true; resets after
response. /_scenario_probe/ is the observable surface for tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12 — Wire providers to consult `current_scenario()`

**Files:**
- Modify: `backend/apps/ai/providers/claude.py`, `openai.py`, `local.py`
- Modify: `backend/apps/market/clients/schwab.py`, `finnhub.py`
- Modify: `backend/apps/files/client.py`

- [ ] **Step 1: Test — claude scenario switch**

Append to `e2e/tests/test_scenario_engine.py`:

```python
@pytest.mark.integration
def test_claude_provider_honors_claude_5xx_scenario(api_base_url: str) -> None:
    """With scenario claude-5xx, creating a snapshot-send-to-AI returns 503 from the provider."""
    import httpx
    # Easiest observable: hit an endpoint that invokes the claude provider directly in mock mode.
    # Use a dedicated dev-only ping view that runs a one-shot provider call.
    r = httpx.post(
        f"{api_base_url}/api/_mock_ping_claude/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=10,
    )
    assert r.status_code == 503 or r.json().get("error_kind") == "provider_503"
```

- [ ] **Step 2: Add `_mock_ping_claude` dev-only endpoint**

In `backend/apps/core/views.py`:

```python
def mock_ping_claude(request):
    """Dev-only — synchronously calls ClaudeProvider.run() and returns the
    first event (or the error status). Only exists under MOCK_EXTERNAL."""
    from apps.ai.providers.claude import ClaudeProvider
    from apps.ai.providers.base import RunRequest

    provider = ClaudeProvider()
    req = RunRequest(model="claude-sonnet-4-6", messages=[{"role": "user", "content": "ping"}])
    try:
        events = list(provider.run(req))
        return JsonResponse({"events": len(events), "first_type": events[0].type if events else None})
    except Exception as e:
        return JsonResponse({"error_kind": type(e).__name__, "detail": str(e)}, status=503)
```

Register in `backend/apps/core/urls.py` under the same `MOCK_EXTERNAL` conditional:

```python
if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true"):
    urlpatterns.append(path("_scenario_probe/", views.scenario_probe, name="scenario-probe"))
    urlpatterns.append(path("_mock_ping_claude/", views.mock_ping_claude, name="mock-ping-claude"))
```

- [ ] **Step 3: Update `ClaudeProvider` mock path**

In `backend/apps/ai/providers/claude.py`, find the `if settings.MOCK_EXTERNAL` branch inside `run()`. Replace with:

```python
if settings.MOCK_EXTERNAL:
    from apps.core.mocks import current_scenario
    from apps.core.mocks.scenarios import handler_for
    from apps.core.mocks import providers as mock_handlers

    handler_name = handler_for(current_scenario(), "claude")
    handler = getattr(mock_handlers, handler_name)
    yield from handler(request)
    return
```

- [ ] **Step 4: Populate handlers in `apps/core/mocks/providers.py`**

Add (keep existing `stream_mocked_response` if present; otherwise add it):

```python
def stream_mocked_response(request):
    from apps.ai.providers.base import Event
    yield Event(type="message_started", data={})
    yield Event(type="text_delta", data={"text": "Mocked response"})
    yield Event(type="usage", data={"input_tokens": 10, "output_tokens": 5})
    yield Event(type="done", data={})


def error_503_prestream(request):
    raise RuntimeError("provider_503: mock scenario claude-5xx")


def stream_then_500(request):
    from apps.ai.providers.base import Event
    yield Event(type="message_started", data={})
    yield Event(type="text_delta", data={"text": "partial"})
    yield Event(type="text_delta", data={"text": " bytes"})
    raise RuntimeError("provider_500: mock scenario claude-5xx-midstream")


def error_429_retry_after(request):
    raise RuntimeError("provider_429_retry_after=30")


def hang_60s(request):
    import time
    time.sleep(60)


def ok(*args, **kwargs):
    return {"status": "ok"}


def error_503(*args, **kwargs):
    raise RuntimeError("provider_503")


def error_401_token_expired(*args, **kwargs):
    raise RuntimeError("401_token_expired")


def oauth_full_flow(*args, **kwargs):
    return {"authorize_url": "http://localhost:8000/schwab/callback?code=MOCK_OAUTH", "tokens": {"access": "mock", "refresh": "mock"}}


def error_500_on_upload(*args, **kwargs):
    raise RuntimeError("files_upload_500")


def stream_tool_use_loop(request):
    from apps.ai.providers.base import Event
    yield Event(type="message_started", data={})
    yield Event(type="tool_call", data={"name": "quotes_now", "input": {"ticker": "AAPL"}})
    yield Event(type="tool_result", data={"output": {"last": 175.0}})
    yield Event(type="text_delta", data={"text": "Result: 175"})
    yield Event(type="usage", data={"input_tokens": 20, "output_tokens": 10})
    yield Event(type="done", data={})


def stream_thinking_heavy(request):
    from apps.ai.providers.base import Event
    yield Event(type="message_started", data={})
    for _ in range(3):
        yield Event(type="thinking_delta", data={"text": "thinking..."})
    yield Event(type="text_delta", data={"text": "here is my answer"})
    yield Event(type="usage", data={"input_tokens": 20, "output_tokens": 30})
    yield Event(type="done", data={})


def structured_observation_report(request):
    from apps.ai.providers.base import Event
    yield Event(type="message_started", data={})
    yield Event(type="text_delta", data={"text": '{"summary":"bullish","signals":[],"risks":[]}'})
    yield Event(type="usage", data={"input_tokens": 30, "output_tokens": 20})
    yield Event(type="done", data={})
```

- [ ] **Step 5: Apply the same dispatch pattern to openai.py, local.py, schwab.py, finnhub.py, files/client.py**

Replace their `if settings.MOCK_EXTERNAL:` blocks with identical `handler_for(current_scenario(), "<service>")` lookups.

- [ ] **Step 6: Pass.**

Run: `docker compose exec web pytest e2e/tests/test_scenario_engine.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/ backend/apps/core/views.py backend/apps/core/urls.py e2e/tests/test_scenario_engine.py
git commit -m "$(cat <<'EOF'
feat(mocks): providers dispatch via scenario registry

Claude/OpenAI/Local/Schwab/Finnhub/Files mock branches now consult
current_scenario() + handler_for(). Adds 13 handler functions in
apps/core/mocks/providers.py covering all v1 scenarios.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13 — `ScenarioClient` + prod-guard test

**Files:**
- Modify: `e2e/mocks/client.py`
- Create: `e2e/api/test_scenario_engine_disabled_in_prod.py`
- Modify: `e2e/conftest.py` — `scenario_client` fixture

- [ ] **Step 1: Test**

Create `e2e/api/test_scenario_engine_disabled_in_prod.py`:

```python
"""Guards that the scenario engine does nothing when MOCK_EXTERNAL=false.

Requires stack to be running WITHOUT the e2e overlay. Skipped under e2e overlay.
"""
from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.integration
def test_header_is_noop_when_mock_external_false(api_base_url: str) -> None:
    if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true"):
        pytest.skip("e2e overlay is up; this test is prod-posture-only")

    r = httpx.get(
        f"{api_base_url}/api/_scenario_probe/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=3,
    )
    # Endpoint shouldn't exist (not registered when MOCK_EXTERNAL=false)
    assert r.status_code == 404
```

- [ ] **Step 2: Fail** — the endpoint is currently registered unconditionally.

(Confirm in Task 11 Step 4 we wrapped it in `if MOCK_EXTERNAL`. If not, wrap now.)

- [ ] **Step 3: Implement ScenarioClient**

Replace `e2e/mocks/client.py`:

```python
"""ScenarioClient — inject X-E2E-Scenario header into both page + api."""
from __future__ import annotations

from typing import Any


class ScenarioClient:
    def __init__(self, page: Any, api: Any) -> None:
        self.page = page
        self.api = api

    def use(self, name: str) -> None:
        self.page.set_extra_http_headers({"X-E2E-Scenario": name})
        self.api.headers["X-E2E-Scenario"] = name

    def reset(self) -> None:
        self.use("default")
```

- [ ] **Step 4: Wire fixture**

Append to `e2e/conftest.py`:

```python
@pytest.fixture
def api_client(api_base_url: str):
    import httpx
    with httpx.Client(base_url=api_base_url, timeout=10) as client:
        yield client


@pytest.fixture
def scenario(page, api_client):
    from e2e.mocks.client import ScenarioClient
    c = ScenarioClient(page, api_client)
    yield c
    c.reset()
```

- [ ] **Step 5: Pass.**

Run: `docker compose exec web pytest e2e/api/test_scenario_engine_disabled_in_prod.py -v`
Expected: PASS or SKIPPED depending on overlay state.

- [ ] **Step 6: Commit**

```bash
git add e2e/mocks/client.py e2e/conftest.py e2e/api/test_scenario_engine_disabled_in_prod.py
git commit -m "$(cat <<'EOF'
feat(e2e): ScenarioClient + scenario pytest fixture

ScenarioClient wraps Playwright page + httpx api client and sets the
X-E2E-Scenario header on both. Added prod-guard test confirming the
engine is a no-op when MOCK_EXTERNAL=false.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 1 acceptance

- [ ] `docker compose exec web pytest e2e/tests/test_seed_ladder.py -v` — 8 tests pass.
- [ ] `docker compose exec web pytest e2e/tests/test_scenario_engine.py -v` — 5 tests pass.
- [ ] `docker compose exec web pytest e2e/api/test_scenario_engine_disabled_in_prod.py -v` — passes or skips.
- [ ] Existing `make e2e-ui` still green (no regression).
- [ ] `apps/core/mocks/` is a package with `providers.py`, `middleware.py`, `scenarios.py`, `__init__.py`.
- [ ] `MOCK_EXTERNAL=true` activates `ScenarioHeaderMiddleware`; `MOCK_EXTERNAL=false` does not.
