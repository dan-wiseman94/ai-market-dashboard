# Thread Snapshot Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire pinned snapshot payload into the on-demand consult/chat thread flow so the LLM actually receives the market data + objective, not just the trading style + user text.

**Architecture:** On `POST /api/threads/` with a `pinned_snapshot_id`, synthesize a `done` user Message whose `content["text"]` is the output of `serialize_for_ai(snap)` and whose `snapshot_ref` points to the snapshot. The existing `_build_request()` in `apps/threads/tasks.py` already filters history by `role__in=["user","assistant"], status="done"`, so the synthetic message is picked up automatically as the first user turn — no changes to the AI pipeline needed. This mirrors the pattern observer/trigger already use (`apps/observer/services/run.py:72-76`, `apps/triggers/tasks.py:170`).

**Tech Stack:** Django 5.1 + DRF; pytest; existing `apps.snapshots.serializer.serialize_for_ai`.

**Scope notes:**
- **In scope:** Text payload (quotes/OHLC/chain/positions/breadth/news/notes + objective) reaches the model on the first user turn of consult/chat threads.
- **Out of scope:** Image attachment via `build_image_blocks` — requires changing `ChatMessage.content` from `str` to `str | list[dict]`. Observer/trigger paths also don't attach images today; fixing that needs its own plan covering multimodal content blocks + provider-level handling.
- **Out of scope:** Re-sending snapshot on every turn. Injection happens once at thread creation; subsequent turns rely on the persisted first message.

---

### Task 1: Failing test — thread creation synthesizes a snapshot user message

**Files:**
- Create: `backend/apps/threads/tests/test_snapshot_injection.py`

- [ ] **Step 1: Write the failing test**

```python
"""Thread creation with a pinned snapshot must synthesize a user message whose
text is the serialized snapshot payload, so the LLM actually sees the market data.

Regression guard for the pre-fix state where `pinned_snapshot` was stored as an FK
but its content never reached the provider call.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import Message, Thread


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="Day trader", style="Aggressive intraday")


@pytest.fixture
def ready_snapshot(db, profile) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile,
        objective="Gauge SPY intraday momentum",
        notes="pre-FOMC",
        status="ready",
        includes=["quotes", "breadth"],
        source="manual",
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done",
        payload={"SPY": {"last": 521.30, "pct_change": 0.42, "bid": 521.28,
                         "ask": 521.31, "volume": 1_234_567, "high": 522.0,
                         "low": 520.1}},
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="breadth", status="done",
        payload={"spy_last": 521.30, "qqq_last": 445.10, "vix_last": 14.2,
                 "sectors": {"XLK": 215.4}, "breadth": {}},
    )
    return snap


def test_thread_create_with_pinned_snapshot_injects_first_user_message(
    db, profile, ready_snapshot,
) -> None:
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={
            "kind": "consult",
            "profile_id": profile.id,
            "pinned_snapshot_id": ready_snapshot.id,
            "title": "SPY read",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content

    thread = Thread.objects.get(id=resp.json()["id"])
    first = Message.objects.filter(thread=thread, role="user").order_by("created_at").first()
    assert first is not None, "expected a synthetic user message"
    assert first.status == "done"
    assert first.snapshot_ref_id == ready_snapshot.id

    text = first.content["text"]
    assert "Gauge SPY intraday momentum" in text, "objective missing from payload"
    assert "SPY" in text and "521.30" in text, "quotes section missing"
    assert "VIX" in text and "14.2" in text, "breadth section missing"


def test_thread_create_without_pinned_snapshot_has_no_synthetic_message(
    db, profile,
) -> None:
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "title": "open chat"},
        format="json",
    )
    assert resp.status_code == 201
    thread = Thread.objects.get(id=resp.json()["id"])
    assert Message.objects.filter(thread=thread).count() == 0


def test_thread_create_with_unknown_snapshot_id_no_crash(db, profile) -> None:
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": 999_999},
        format="json",
    )
    assert resp.status_code == 201
    thread = Thread.objects.get(id=resp.json()["id"])
    assert thread.pinned_snapshot is None
    assert Message.objects.filter(thread=thread).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec web pytest backend/apps/threads/tests/test_snapshot_injection.py -v
```

Expected: `test_thread_create_with_pinned_snapshot_injects_first_user_message` FAILS with `expected a synthetic user message` (the other two pass — they're regression guards that must keep passing after the fix).

---

### Task 2: Implement snapshot injection in thread creation

**Files:**
- Modify: `backend/apps/threads/views.py:34-48`

- [ ] **Step 1: Update `ThreadViewSet.create()` to synthesize the first message**

Replace the existing `create` method body (currently lines 34-48) with:

```python
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        data = request.data
        profile = None
        if pid := data.get("profile_id"):
            profile = TradingProfile.objects.filter(id=pid).first()
        snap = None
        if sid := data.get("pinned_snapshot_id"):
            snap = Snapshot.objects.filter(id=sid).first()
        t = Thread.objects.create(
            kind=data.get("kind", "consult"),
            title=data.get("title", ""),
            profile=profile,
            pinned_snapshot=snap,
        )
        if snap is not None:
            Message.objects.create(
                thread=t, role="user",
                content={"text": serialize_for_ai(snap)},
                snapshot_ref=snap, status="done",
            )
        return Response(ThreadSerializer(t).data, status=201)
```

- [ ] **Step 2: Add the import**

At the top of `backend/apps/threads/views.py`, add:

```python
from apps.snapshots.serializer import serialize_for_ai
```

The existing imports already cover `Message`, `Thread`, `Snapshot`, `TradingProfile`, `ThreadSerializer` — no other changes.

- [ ] **Step 3: Run the new tests to verify they pass**

```bash
docker compose exec web pytest backend/apps/threads/tests/test_snapshot_injection.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 4: Run the full threads test module to catch regressions**

```bash
docker compose exec web pytest backend/apps/threads/tests/ -v
```

Expected: all tests PASS. If `test_endpoints.py::test_create_thread_with_pinned_snapshot` (or similar) now sees one extra message, that's expected behavior; update the test's expectation if it asserted `messages.count() == 0` pre-fix.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/threads/views.py backend/apps/threads/tests/test_snapshot_injection.py
git commit -m "$(cat <<'EOF'
fix(threads): inject snapshot payload into consult thread first message

Thread.pinned_snapshot was stored but never reached the provider call — the
LLM saw only profile.style + user text, not the market data. Mirror the
observer/trigger pattern by synthesizing a done user message containing
serialize_for_ai(snap) at thread creation so _build_request() picks it up
via history naturally.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Integration test — `_build_request()` sends snapshot text to the provider

**Files:**
- Modify: `backend/apps/threads/tests/test_snapshot_injection.py` (append)

- [ ] **Step 1: Add an integration test that calls `_build_request` directly**

Append to `backend/apps/threads/tests/test_snapshot_injection.py`:

```python
def test_build_request_includes_snapshot_on_first_user_turn(
    db, profile, ready_snapshot,
) -> None:
    """After thread creation + one user follow-up, _build_request should emit
    [system=profile.style, user=snapshot_markdown, user=follow_up]."""
    from apps.threads.tasks import _build_request

    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={
            "kind": "consult",
            "profile_id": profile.id,
            "pinned_snapshot_id": ready_snapshot.id,
        },
        format="json",
    )
    thread_id = resp.json()["id"]
    thread = Thread.objects.select_related("profile").get(id=thread_id)

    follow_up = Message.objects.create(
        thread=thread, role="user",
        content={"text": "What do you see?"}, status="done",
    )

    req = _build_request(thread, follow_up)
    assert req.system == "Aggressive intraday"
    assert len(req.messages) == 2
    assert req.messages[0].role == "user"
    assert "Gauge SPY intraday momentum" in req.messages[0].content
    assert "SPY" in req.messages[0].content
    assert req.messages[1].role == "user"
    assert req.messages[1].content == "What do you see?"
```

- [ ] **Step 2: Run it**

```bash
docker compose exec web pytest backend/apps/threads/tests/test_snapshot_injection.py::test_build_request_includes_snapshot_on_first_user_turn -v
```

Expected: PASS (Task 2 already makes this work — this test just locks the end-to-end contract).

- [ ] **Step 3: Commit**

```bash
git add backend/apps/threads/tests/test_snapshot_injection.py
git commit -m "$(cat <<'EOF'
test(threads): lock snapshot-first-turn contract via _build_request

Guards against future regressions where someone refactors _build_request or
thread creation and silently drops the snapshot from the provider call.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Update CLAUDE.md with the convention

**Files:**
- Modify: `/home/dan/ai-dashboard/CLAUDE.md`

- [ ] **Step 1: Add the convention to the "Non-obvious conventions" section**

Find the section `## Non-obvious conventions` in `CLAUDE.md`. Add this bullet in alphabetical position (after the existing bullets around threads/observer):

```markdown
- **Pinned snapshots reach the LLM as a synthetic first user turn.** When a thread is created with `pinned_snapshot_id`, `ThreadViewSet.create()` synthesizes a `done` user `Message` whose `content["text"]` is `serialize_for_ai(snap)` and `snapshot_ref=snap`. The existing `_build_request()` in `apps/threads/tasks.py` picks it up via the history query (`role__in=["user","assistant"], status="done"`). Observer/trigger paths use the same pattern per-fire (`apps/observer/services/run.py:72`). **Do not** load the snapshot inside `_build_request()` — the synthetic-message pattern keeps the AI pipeline provider-agnostic and gives the UI a visible record of what the model saw.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): document snapshot → first-user-turn convention

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Run the full check gate and verify green

- [ ] **Step 1: Lint + full test suite**

```bash
make check
```

Expected: exit 0. All backend + frontend tests pass, ruff + mypy + eslint clean.

- [ ] **Step 2: If `make check` passes, the fix is complete**

If any pre-existing failure surfaces that is unrelated to this change, note it but do not in-scope it here — the core value loop restoration is the shippable unit.

---

## Post-plan: known follow-ups (not in this plan)

These came out of the fit-for-purpose assessment but belong to separate plans:

1. **Image attachment pipeline** — `build_image_blocks` is never called in production (observer, trigger, and threads all omit it). Requires refactoring `ChatMessage.content` to `str | list[dict]` and threading vision content through all three providers. Create a dedicated spec/plan before touching.
2. **Monthly cost-cap enforcement** — `daily_cost_cap_usd` is gated at `apps/threads/tasks.py:166`, but `monthly_cost_cap_usd` on `ProviderConfig` is stored-and-reported only, never checked. Small fix: extend `check_daily_cap` in `apps/ai/cost.py` or add a sibling `check_monthly_cap`.
3. **Single-instance locks on beat tasks** — `observer.run_observer_task` and `triggers.evaluate_triggers` lack overlap/restart guards; `fire_trigger` already shows the Redis-lock pattern (`apps/triggers/tasks.py:92-101`).
4. **Quote freshness timestamps** — `apps/market/services/quotes.py` returns no `ts` on quote dicts, so `_render_quotes` emits staleness-blind tables.
