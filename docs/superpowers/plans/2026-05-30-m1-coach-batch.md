# M1 Coach Batch (W5–W8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Decision Coach context richer (semantic recall + a lessons-learned block) and ensure it is injected on the trigger path too — without ever raising into the request path.

**Architecture:** The coach assembles a compact, deterministic "what you already know" block in `apps/threads/coach.py`; `assemble_coach_context(snapshot, profile)` is the single chokepoint that gates on `profile.enable_coach`, requires a `snapshot.primary_ticker`, isolates every sub-section behind `_safe()`, and returns `""` when there's nothing to say. W6 swaps the recall sub-section from pure-recency (`related_to_ticker`) to bounded semantic `search()` seeded by a situation query. W7 adds `_lessons_block(ticker)` from decisive post-mortems via a lazy `apps.thesis.models.PostMortem` import (threads→thesis cycle rule). W8 wires `assemble_coach_context` into the trigger fire path (`apps/triggers/tasks.py::_do_fire`), mirroring `apps/observer/services/run.py`. W5 records the verified coverage map as a module docstring and adds a cross-path regression.

**Tech Stack:** Django, DRF, pytest, pgvector/fastembed recall, Celery (trigger/observer tasks)

---

## Ground-truth facts (verified by reading the code — do NOT deviate)

- `apps/threads/coach.py`:
  - `build_system_prompt(profile, *, now: datetime) -> str` is **pure** (profile + clock). It does **NOT** take a snapshot and does **NOT** call `assemble_coach_context`. It returns `profile.style` (or base-framing + style) and is the SYSTEM-prompt builder.
  - `assemble_coach_context(snapshot, profile) -> str` is the coach chokepoint. It returns `""` when `profile is None` / `not getattr(profile, "enable_coach", False)` / `not getattr(snapshot, "primary_ticker", None)` / all sub-sections empty. It runs four `_safe(...)`-wrapped sub-sections and joins non-empty ones with `"\n\n"`, then wraps with header `"## 🧭 What you already know  (auto-assembled context — may be incomplete)"` and a trailing `"\n\n"`.
  - `_recall_block(ticker: str) -> str` (takes **only** `ticker`) currently calls `from apps.recall.services.search import related_to_ticker` then `related_to_ticker(ticker, k=5)`. It iterates **dict** hits: `h.get("source_created_at")`, `h.get("kind")`, `h.get("snippet", "")`, `h.get("link", "")`. Its header line is `"### You've noted this before"`.
  - `_theses_block(ticker: str, snapshot) -> str` does a **function-local** `from apps.thesis.models import Thesis` (the cycle-safe pattern to mirror).
  - `_safe(fn, default="") -> str` swallows exceptions and returns `default`.
- `apps/recall/services/search.py`:
  - `search(q: str, *, k: int = 10, kinds=None, ticker=None) -> list[dict]`. It `embed([q])`; if vectors present → cosine order; else FTS fallback (`SearchQuery`/`SearchRank`). Returns `[_hit(d) for d in qs[:k]]`.
  - `_hit(d)` returns a **dict**: `{"kind", "object_id", "snippet" (text[:280]), "source_created_at", "tickers", "link"}`.
  - `_filtered(qs, kinds, ticker)` applies `kind__in=kinds` and `tickers__contains=[ticker.upper()]`.
  - `related_to_ticker(ticker, *, k=5) -> list[dict]` — recency-only.
- `apps/recall/models.py`: `RecallDocument` has `kind` (CharField, `KIND_CHOICES` plain strings: `message/snapshot/thesis/journal/observation/postmortem`), `object_id` (IntegerField), `tickers` (JSONField list), `text`, `embedding`, `source_created_at`. **No `RecallDocument.Kind` enum. No `ticker` (singular) field. No `source_id`/`title` fields.**
- `apps/recall/tests/test_search.py`: builder is `_doc(oid, vec, text="hello", ticker="NVDA")` — kind hardcoded `"thesis"`, sets `object_id=oid`, `embedding=vec`, `tickers=[ticker]`, `content_hash=str(oid)`. Tests monkeypatch `S.embed`. Hits are dicts asserted via `h["object_id"]`.
- `apps/recall/embeddings.py`: `embed(texts)` returns `None` when fastembed is unavailable, so `search()` takes the FTS branch in test/dev.
- `apps/threads/tests/test_coach.py`: `NOW = datetime(2026,5,29,14,30,tzinfo=UTC)`. `coach_profile` fixture = `TradingProfile.objects.create(name="c", style="s")` (enable_coach defaults True). `_snap(profile, *, ticker="NVDA", last=188.2)` creates a `Snapshot(profile=, status="ready", includes=["quotes"], source="manual", primary_ticker=ticker)` + a `SnapshotSection(kind="quotes", status="done", payload={ticker: {"last": last}})`. Theses built via `Thesis.objects.create(title=, ticker=, direction="bullish", conviction=4, status="open", target_price=...)`.
- `apps/profiles/models.py`: `TradingProfile.enable_coach = BooleanField(default=True)`. Also `style`, `default_provider="claude"`, `default_model`, `default_includes`.
- `apps/triggers/models.py`: model is **`EventTrigger`** (not `Trigger`); `profile = FK(profiles.TradingProfile)`, `name`, `condition`. `TriggerFiring` has `trigger`, `snapshot`, `thread`, `matched_values`, `cost_capped`.
- `apps/triggers/tasks.py`: fire path is `fire_trigger(trigger_id, matched_values)` → `_do_fire(*, trigger_id, matched_values)`. `_do_fire` does `trigger = EventTrigger.objects.select_related("profile").get(id=trigger_id)`, captures `snap = capture(profile=trigger.profile, objective=..., includes=trigger.profile.default_includes, source="trigger")`, then builds the user turn (lines ~184-194):
  ```python
  user_msg = Message.objects.create(
      thread=thread,
      role="user",
      content={
          "text": serialize_for_ai(
              snap, provider=provider_name, model=trigger.profile.default_model
          )
      },
      snapshot_ref=snap,
      status="done",
  )
  run_ai_on_message.delay(thread_id=thread.id, user_message_id=user_msg.id)
  ```
  where `provider_name = trigger.profile.default_provider`. There is currently **no** coach call here.
- `apps/observer/services/run.py` (the mirror): line 100 `coach = assemble_coach_context(snap, sched.profile)` is called **unconditionally** (NO `if enable_coach` guard at the call site — gating is internal to `assemble_coach_context`), then the user turn is `content={"text": coach + payload_text}` (line 105). Import at top: `from apps.threads.coach import assemble_coach_context, build_system_prompt`.
- THREADS path coach injection lives in `apps/threads/views.py` (`ThreadViewSet.create`, ~line 84): `coach = assemble_coach_context(snap, profile)` prepended to the synthetic pinned-snapshot user message. **Not** in `build_system_prompt`.
- `apps/thesis/models.py`: `PostMortem` fields: `thesis` (FK→Thesis), `horizon_days` (int), `due_at` (DateTimeField, **required, no default**), `status` (CharField, `STATUS_CHOICES` plain strings incl. `"done"`), `forward_return_pct` (FloatField, nullable), `verdict` (CharField, `VERDICT_CHOICES`: `correct/incorrect/mixed/inconclusive`, blank default `""`), `report` (**JSONField(default=dict)**, free-form), `completed_at` (nullable). **No `scheduled_for`. No `PostMortem.Status`/`.Verdict` enums.** Ticker lives on `PostMortem.thesis.ticker`. `Thesis.title`, `Thesis.status` choices `open/closed_win/closed_loss/closed_scratch/invalidated`, `Thesis.direction` `bullish/bearish/neutral`.
- `report` is a free-form `JSONField(default=dict)` populated by `report.model_dump()` of `PostMortemReport` (the AI narrative; may be `{}` when no key/non-claude). Because it's free-form JSON, `_lessons_block` reads it **defensively** (any list-of-strings under `lessons` / `what_missed`) and the tests inject the dict literally — so the block does not couple to the exact schema field names.

---

## File Structure

**Modified**
- `backend/apps/recall/services/search.py` — add `related_to_situation(ticker, query, *, k=3, kinds=None) -> list[dict]`: a thin wrapper over `search()` that ticker-scopes, kind-filters, and bounds `k`, returns `[]` for empty ticker, and degrades exactly as `search()` (semantic → FTS → empty). One responsibility: situation-seeded, ticker-scoped, kind-filtered recall returning the same dict-hit shape `_recall_block` already consumes.
- `backend/apps/threads/coach.py` — (W6) `_recall_block(snap, ticker)` calls `related_to_situation` with a compact situation query; add `_situation_query(snap, ticker)` + `_RECALL_KINDS`. (W7) add `_lessons_block(ticker)` and wire it into `assemble_coach_context`. (W5) extend the module docstring with the verified coverage map.
- `backend/apps/triggers/tasks.py` — (W8) in `_do_fire`, build `coach = assemble_coach_context(snap, trigger.profile)` (lazy import) and prepend it to the serialized user-turn text, mirroring observer.

**Tests (added)**
- `backend/apps/recall/tests/test_search.py` — `related_to_situation` filter/bound/empty-ticker tests.
- `backend/apps/threads/tests/test_coach.py` — semantic-recall-block test, lessons-block tests, W5 cross-path parity test.
- `backend/apps/triggers/tests/test_fire_trigger_task.py` — coach-injected-on-fire test.

**No new files, no migrations, no new models.**

---

### Task 1: Add `related_to_situation` helper to recall search (W6 dependency)

**Files:**
- Modify: `backend/apps/recall/services/search.py`
- Test: `backend/apps/recall/tests/test_search.py` (RUN: `apps/recall/tests/test_search.py`)

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/recall/tests/test_search.py` (the file already imports `pytest`, `RecallDocument`, and `from apps.recall.services import search as S`, and defines `_doc(oid, vec, text="hello", ticker="NVDA")`). These tests force the FTS branch by monkeypatching `S.embed` to return `None`, and seed an FTS vector exactly as the existing `test_fts_fallback_when_no_embedding` does:

```python
@pytest.mark.django_db
def test_related_to_situation_empty_ticker_returns_empty():
    assert S.related_to_situation("", "anything") == []


@pytest.mark.django_db
def test_related_to_situation_filters_kind_and_ticker(monkeypatch):
    from django.contrib.postgres.search import SearchVector

    monkeypatch.setattr(S, "embed", lambda texts: None)  # force FTS branch
    keep = RecallDocument.objects.create(
        kind="thesis", object_id=1, text="nvidia earnings beat",
        tickers=["NVDA"], content_hash="1",
    )
    RecallDocument.objects.create(
        kind="snapshot", object_id=2, text="nvidia earnings beat",
        tickers=["NVDA"], content_hash="2",
    )  # excluded by kind filter
    RecallDocument.objects.create(
        kind="thesis", object_id=3, text="nvidia earnings beat",
        tickers=["SPY"], content_hash="3",
    )  # excluded by ticker filter
    RecallDocument.objects.filter(pk__in=[keep.pk]).update(search=SearchVector("text"))

    hits = S.related_to_situation(
        "NVDA", "earnings", k=5, kinds=["thesis", "observation", "postmortem"]
    )
    assert {h["object_id"] for h in hits} == {1}


@pytest.mark.django_db
def test_related_to_situation_respects_k_bound(monkeypatch):
    from django.contrib.postgres.search import SearchVector

    monkeypatch.setattr(S, "embed", lambda texts: None)
    for i in range(5):
        d = RecallDocument.objects.create(
            kind="thesis", object_id=10 + i, text="nvidia earnings beat",
            tickers=["NVDA"], content_hash=str(10 + i),
        )
        RecallDocument.objects.filter(pk=d.pk).update(search=SearchVector("text"))
    hits = S.related_to_situation("NVDA", "earnings", k=2, kinds=["thesis"])
    assert len(hits) <= 2
```

- [ ] **Step 2: Run test, verify it fails**

```
docker compose exec web pytest apps/recall/tests/test_search.py::test_related_to_situation_empty_ticker_returns_empty -v
```

Expected failure: `AttributeError: module 'apps.recall.services.search' has no attribute 'related_to_situation'`.

- [ ] **Step 3: Implement**

In `backend/apps/recall/services/search.py`, add directly below the existing `related_to_ticker` function (keep `related_to_ticker` — it's still used elsewhere/tested):

```python
def related_to_situation(
    ticker: str, query: str, *, k: int = 3, kinds=None
) -> list[dict]:
    """Situation-seeded, ticker-scoped semantic recall.

    Thin wrapper over :func:`search`: scopes to ``ticker``, optionally filters to
    ``kinds``, and bounds results to ``k``. Returns ``[]`` for an empty ticker and
    degrades exactly as ``search`` (semantic -> FTS -> empty). Returns the same
    dict-hit shape ``search`` does.
    """
    if not ticker:
        return []
    return search(query or ticker, k=k, kinds=kinds, ticker=ticker)
```

(No recency re-sort needed: `search()`'s FTS branch already orders by `-rank` and the semantic branch by cosine distance; `RecallDocument.source_created_at` is not a stable tiebreak across both paths, so we keep the helper minimal and rely on `search`'s ordering + the `k` bound. The coach below caps `k` at 3.)

- [ ] **Step 4: Run test, verify pass**

```
docker compose exec web pytest apps/recall/tests/test_search.py -v
```

Expected: the three new tests pass alongside the existing `test_semantic_search_orders_by_cosine`, `test_fts_fallback_when_no_embedding`, `test_ticker_filter`.

- [ ] **Step 5: Commit**

```
git add backend/apps/recall/services/search.py backend/apps/recall/tests/test_search.py && git commit -m "feat(recall): add situation-seeded related_to_situation helper"
```

---

### Task 2: Switch coach recall block to semantic search (W6)

**Files:**
- Modify: `backend/apps/threads/coach.py`
- Test: `backend/apps/threads/tests/test_coach.py` (RUN: `apps/threads/tests/test_coach.py`)

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/threads/tests/test_coach.py` (already imports `assemble_coach_context`, `build_system_prompt`, `Thesis`, `TradingProfile`, `Snapshot`, `SnapshotSection`, `NOW`, and defines fixtures `coach_profile` + `_snap`). This test patches the new `related_to_situation` on the coach module to assert the coach calls it with the ticker, a situation query containing the ticker, the bounded `k`, and the decisive kinds — deterministic regardless of fastembed/FTS:

```python
@pytest.mark.django_db
def test_recall_block_uses_situation_search(coach_profile, monkeypatch):
    from apps.threads import coach as coach_mod

    snap = _snap(coach_profile)  # primary_ticker NVDA, quotes section last=188.2
    captured = {}

    def fake(ticker, query, *, k, kinds):
        captured["ticker"] = ticker
        captured["query"] = query
        captured["k"] = k
        captured["kinds"] = kinds
        return [
            {
                "kind": "postmortem",
                "object_id": 7,
                "snippet": "NVDA ran into earnings",
                "source_created_at": NOW,
                "tickers": ["NVDA"],
                "link": "/theses/7",
            }
        ]

    monkeypatch.setattr(coach_mod, "related_to_situation", fake)
    out = coach_mod._recall_block(snap, "NVDA")

    assert captured["ticker"] == "NVDA"
    assert "NVDA" in captured["query"]
    assert captured["k"] == coach_mod._MAX_RECALL_ITEMS
    assert set(captured["kinds"]) == {"postmortem", "thesis", "observation"}
    assert "### You've noted this before" in out
    assert "NVDA ran into earnings" in out


@pytest.mark.django_db
def test_recall_block_empty_ticker_returns_empty(coach_profile):
    from apps.threads.coach import _recall_block

    assert _recall_block(_snap(coach_profile), "") == ""
```

- [ ] **Step 2: Run test, verify it fails**

```
docker compose exec web pytest apps/threads/tests/test_coach.py::test_recall_block_uses_situation_search -v
```

Expected failure: `TypeError: _recall_block() takes 1 positional argument but 2 were given` (current signature is `_recall_block(ticker)`), and/or `AttributeError: ... has no attribute 'related_to_situation'`.

- [ ] **Step 3: Implement**

In `backend/apps/threads/coach.py`:

3a. Add module-level caps near the top of the module body (just after `log = logging.getLogger(__name__)`):

```python
# Recall sub-block bounds: at most N semantically-related past notes, scoped to a
# short situation query. Kinds worth recalling into the coach (not raw messages/snapshots).
_MAX_RECALL_ITEMS = 3
_RECALL_QUERY_MAX_CHARS = 400
_RECALL_KINDS = ("postmortem", "thesis", "observation")
```

3b. Add a compact situation-query helper next to the other private helpers (e.g., just above `_recall_block`):

```python
def _situation_query(snapshot, ticker: str) -> str:
    """A short free-text query describing the current situation for recall.

    Ticker + a couple of headline numbers from the snapshot's own quotes section
    (no fetch). Bounded to _RECALL_QUERY_MAX_CHARS so the embed/FTS call stays cheap.
    """
    parts = [ticker]
    last = _snapshot_last(snapshot, ticker)
    if last is not None:
        parts.append(f"last {_fmt_num(last)}")
    return " ".join(parts)[:_RECALL_QUERY_MAX_CHARS]
```

3c. Replace the existing `_recall_block` (current body imports `related_to_ticker` and calls `related_to_ticker(ticker, k=5)`):

```python
def _recall_block(ticker: str) -> str:
    from apps.recall.services.search import related_to_ticker

    hits = related_to_ticker(ticker, k=5)
    if not hits:
        return ""
    lines = ["### You've noted this before"]
    for h in hits:
        when = h.get("source_created_at")
        when_s = when.strftime("%Y-%m-%d") if hasattr(when, "strftime") else str(when or "?")
        lines.append(
            f'- {when_s} ({h.get("kind")}): "{h.get("snippet", "")}" → {h.get("link", "")}'
        )
    return "\n".join(lines)
```

with:

```python
def _recall_block(snapshot, ticker: str) -> str:
    if not ticker:
        return ""
    query = _situation_query(snapshot, ticker)
    hits = related_to_situation(
        ticker, query, k=_MAX_RECALL_ITEMS, kinds=list(_RECALL_KINDS)
    )
    if not hits:
        return ""
    lines = ["### You've noted this before"]
    for h in hits:
        when = h.get("source_created_at")
        when_s = when.strftime("%Y-%m-%d") if hasattr(when, "strftime") else str(when or "?")
        lines.append(
            f'- {when_s} ({h.get("kind")}): "{h.get("snippet", "")}" → {h.get("link", "")}'
        )
    return "\n".join(lines)
```

3d. Add the module-top import (so `monkeypatch.setattr(coach_mod, "related_to_situation", ...)` resolves on the coach module). Below the existing `from django.conf import settings` line, add:

```python
from apps.recall.services.search import related_to_situation
```

(This is a top-of-module import of a recall helper. `apps.recall.services.search` imports only Django/pgvector + `apps.recall.*` — it does NOT import `apps.threads` or `apps.thesis`, so it does not create the threads→thesis cycle. `_recall_block`'s old function-local `related_to_ticker` import is removed since it's no longer used.)

3e. Update the `assemble_coach_context` call site — the existing line is `_safe(lambda: _recall_block(ticker))`; change it to pass the snapshot:

```python
        _safe(lambda: _recall_block(snapshot, ticker)),
```

- [ ] **Step 4: Run test, verify pass**

```
docker compose exec web pytest apps/threads/tests/test_coach.py -v
```

Expected: new tests pass. Pre-existing tests still pass, in particular `test_coach_empty_when_no_history` (FTS finds nothing → `related_to_situation` returns `[]` → recall block empty) and `test_coach_never_raises_when_a_subsource_throws` — note that test monkeypatches `apps.recall.services.search.related_to_ticker` to raise. After this task the coach no longer calls `related_to_ticker`, so the patched function is never hit; the test still asserts the coach does not raise AND the healthy theses block renders, which both hold. **Update that test's patch target** to the new dependency so it keeps asserting the recall failure path: in `test_coach_never_raises_when_a_subsource_throws` change `monkeypatch.setattr("apps.recall.services.search.related_to_ticker", boom)` to `monkeypatch.setattr("apps.threads.coach.related_to_situation", boom)` (patch the name the coach actually calls). Re-run to confirm green.

- [ ] **Step 5: Commit**

```
git add backend/apps/threads/coach.py backend/apps/threads/tests/test_coach.py && git commit -m "feat(threads): coach recall uses semantic situation search (W6)"
```

---

### Task 3: Add lessons-learned block to the coach (W7)

**Files:**
- Modify: `backend/apps/threads/coach.py`
- Test: `backend/apps/threads/tests/test_coach.py` (RUN: `apps/threads/tests/test_coach.py`)

Decisive = `verdict in {"correct", "incorrect"}`, `status="done"` (look-ahead-safe: a horizon-H post-mortem only completes ≥H days after the thesis opened). Newest-first by `-completed_at`. Ticker via `thesis__ticker`. Lazy-import `PostMortem` (cycle rule). `report` is free-form JSON read defensively. Hard cap 2 post-mortems × 2 bullets.

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/threads/tests/test_coach.py`. `PostMortem.due_at` is required; `from datetime import UTC, datetime, timedelta` is already imported at the top of the file:

```python
@pytest.mark.django_db
def test_lessons_block_renders_decisive_postmortems(coach_profile):
    from apps.thesis.models import PostMortem, Thesis
    from apps.threads.coach import _lessons_block

    t = Thesis.objects.create(
        title="Earnings run", ticker="NVDA", direction="bullish",
        conviction=4, status="closed_loss",
    )
    pm = PostMortem.objects.create(
        thesis=t, horizon_days=30, due_at=NOW, status="done",
        verdict="incorrect", forward_return_pct=-5.0,
        report={
            "lessons": ["Size smaller into earnings", "Wait for the IV crush"],
            "what_missed": ["Guidance was already priced in"],
        },
    )
    PostMortem.objects.filter(pk=pm.pk).update(completed_at=NOW)

    out = _lessons_block("NVDA")
    assert "### Lessons learned" in out
    assert "incorrect" in out
    assert "30d" in out
    assert "Size smaller into earnings" in out


@pytest.mark.django_db
def test_lessons_block_ignores_inconclusive_and_unfinished(coach_profile):
    from apps.thesis.models import PostMortem, Thesis
    from apps.threads.coach import _lessons_block

    t = Thesis.objects.create(
        title="x", ticker="NVDA", direction="bullish", conviction=3, status="open"
    )
    PostMortem.objects.create(  # inconclusive -> excluded
        thesis=t, horizon_days=7, due_at=NOW, status="done",
        verdict="inconclusive", report={"lessons": ["nope"]},
    )
    PostMortem.objects.create(  # still scheduled -> excluded
        thesis=t, horizon_days=90, due_at=NOW, status="scheduled",
        verdict="correct", report={"lessons": ["also nope"]},
    )
    assert _lessons_block("NVDA") == ""


@pytest.mark.django_db
def test_lessons_block_caps_at_two(coach_profile):
    from apps.thesis.models import PostMortem, Thesis
    from apps.threads.coach import _lessons_block

    for i in range(4):
        t = Thesis.objects.create(
            title=f"t{i}", ticker="NVDA", direction="bullish", conviction=3, status="open"
        )
        pm = PostMortem.objects.create(
            thesis=t, horizon_days=30, due_at=NOW, status="done",
            verdict="correct", forward_return_pct=4.0, report={"lessons": [f"lesson {i}"]},
        )
        PostMortem.objects.filter(pk=pm.pk).update(completed_at=NOW)
    out = _lessons_block("NVDA")
    # At most 2 post-mortem bullet headers (one per pm) rendered.
    assert out.count("[correct, 30d]") == 2


def test_lessons_block_empty_ticker():
    from apps.threads.coach import _lessons_block

    assert _lessons_block("") == ""


@pytest.mark.django_db
def test_assemble_includes_lessons_block(coach_profile):
    from apps.thesis.models import PostMortem, Thesis

    t = Thesis.objects.create(
        title="y", ticker="NVDA", direction="bearish", conviction=2, status="closed_win"
    )
    pm = PostMortem.objects.create(
        thesis=t, horizon_days=90, due_at=NOW, status="done",
        verdict="correct", forward_return_pct=8.0,
        report={"lessons": ["Trust the breadth signal"]},
    )
    PostMortem.objects.filter(pk=pm.pk).update(completed_at=NOW)

    out = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert "🧭 What you already know" in out
    assert "### Lessons learned" in out
    assert "Trust the breadth signal" in out
```

- [ ] **Step 2: Run test, verify it fails**

```
docker compose exec web pytest apps/threads/tests/test_coach.py::test_lessons_block_renders_decisive_postmortems -v
```

Expected failure: `ImportError: cannot import name '_lessons_block' from 'apps.threads.coach'`.

- [ ] **Step 3: Implement**

3a. Add caps near the other constants in `coach.py` (below `_RECALL_KINDS`):

```python
# Lessons block: at most this many decisive post-mortems, each with <=2 bullets.
_MAX_LESSONS = 2
_MAX_LESSON_BULLETS = 2
# Free-form report keys that hold lesson bullets (read defensively; report is JSON).
_LESSON_REPORT_KEYS = ("lessons", "what_missed")
```

3b. Add `_lessons_block` directly below `_theses_block` (mirroring its function-local thesis import + early `if not ticker` guard):

```python
def _lessons_block(ticker: str) -> str:
    """Top decisive post-mortems for the ticker, newest first, with lessons.

    Reads only ``status="done"`` post-mortems with a decisive verdict
    (correct/incorrect) — look-ahead-safe by construction, since a horizon-H
    post-mortem only completes >=H days after the thesis opened. Lazy-imports
    PostMortem to respect the threads->thesis import cycle. Never raises (caller
    wraps it in _safe; this body also tolerates missing/odd report shapes).
    """
    if not ticker:
        return ""
    from apps.thesis.models import PostMortem

    rows = list(
        PostMortem.objects.filter(
            thesis__ticker=ticker.upper(),
            status="done",
            verdict__in=["correct", "incorrect"],
        )
        .select_related("thesis")
        .order_by("-completed_at")[:_MAX_LESSONS]
    )
    if not rows:
        return ""
    lines = ["### Lessons learned"]
    for pm in rows:
        title = (pm.thesis.title or "").strip() or f"thesis #{pm.thesis_id}"
        lines.append(f"- {title} [{pm.verdict}, {pm.horizon_days}d]")
        report = pm.report if isinstance(pm.report, dict) else {}
        bullets: list[str] = []
        for key in _LESSON_REPORT_KEYS:
            val = report.get(key)
            if isinstance(val, list):
                bullets.extend(str(x).strip() for x in val if str(x).strip())
        for bullet in bullets[:_MAX_LESSON_BULLETS]:
            lines.append(f"  - {bullet}")
    return "\n".join(lines)
```

3c. Wire it into `assemble_coach_context` — add a `_safe`-wrapped entry to the `sections` list (after the `_recall_block` entry):

```python
    sections = [
        _safe(lambda: _theses_block(ticker, snapshot)),
        _safe(lambda: _diff_block(snapshot)),
        _safe(lambda: _track_record_block(ticker)),
        _safe(lambda: _recall_block(snapshot, ticker)),
        _safe(lambda: _lessons_block(ticker)),
    ]
```

- [ ] **Step 4: Run test, verify pass**

```
docker compose exec web pytest apps/threads/tests/test_coach.py -v
```

Expected: all five lessons tests pass; pre-existing tests still pass (`test_coach_empty_when_no_history` stays empty because there are no done post-mortems).

- [ ] **Step 5: Commit**

```
git add backend/apps/threads/coach.py backend/apps/threads/tests/test_coach.py && git commit -m "feat(threads): add lessons-learned coach block from decisive post-mortems (W7)"
```

---

### Task 4: Inject the coach on the trigger fire path (W8)

**Files:**
- Modify: `backend/apps/triggers/tasks.py`
- Test: `backend/apps/triggers/tests/test_fire_trigger_task.py` (RUN: `apps/triggers/tests/test_fire_trigger_task.py`)

Mirror observer exactly: call `assemble_coach_context(snap, trigger.profile)` (the chokepoint gates on `enable_coach` + `primary_ticker` internally) and prepend to the serialized user text. A trigger snapshot is captured with `trigger.profile.default_includes`; if that includes `"quotes"` the snapshot gets a `primary_ticker`, and the coach can emit a block — otherwise `assemble_coach_context` returns `""` harmlessly.

- [ ] **Step 1: Write the failing test**

First READ `backend/apps/triggers/tests/test_fire_trigger_task.py` to reuse its EXACT fixtures/builders (how it builds an `EventTrigger` + `TradingProfile`, how it patches `apps.triggers.tasks.capture`, `serialize_for_ai`, `run_ai_on_message`, `_redis`/the fire lock, and `ProviderConfig`). Add a test modeled on the existing happy-path fire test but enabling the coach and seeding an open thesis + a `primary_ticker` snapshot. The skeleton below names the collaborators that MUST be patched (match the existing test's patch style verbatim — same `mock.patch` targets it already uses):

```python
@pytest.mark.django_db
def test_fire_trigger_injects_coach_when_enabled(monkeypatch):
    """W8: when the profile enables the coach and the captured snapshot has a
    primary_ticker, the trigger user-turn is prefixed with the coach block."""
    from unittest import mock

    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotSection
    from apps.thesis.models import Thesis
    from apps.threads.models import Message
    from apps.triggers import tasks as trig_tasks
    from apps.triggers.models import EventTrigger

    profile = TradingProfile.objects.create(
        name="coach", style="s", enable_coach=True, default_includes=["quotes"]
    )
    trig = EventTrigger.objects.create(
        name="T", profile=profile, condition={"all": []}
    )
    snap = Snapshot.objects.create(
        profile=profile, status="ready", includes=["quotes"],
        source="trigger", primary_ticker="NVDA",
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"NVDA": {"last": 188.2}}
    )
    Thesis.objects.create(
        title="AI capex", ticker="NVDA", direction="bullish",
        conviction=4, status="open", target_price=210,
    )

    # Patch the same collaborators the existing happy-path fire test patches:
    #   capture -> return our snap; serialize_for_ai -> "SNAP_TEXT";
    #   run_ai_on_message.delay -> no-op; the redis fire-lock -> always acquire.
    monkeypatch.setattr(trig_tasks, "capture", lambda **kw: snap)
    monkeypatch.setattr(trig_tasks, "serialize_for_ai", lambda *a, **k: "SNAP_TEXT")
    monkeypatch.setattr(trig_tasks.run_ai_on_message, "delay", lambda **kw: None)

    fake_redis = mock.MagicMock()
    fake_redis.set.return_value = True  # acquire the fire lock
    monkeypatch.setattr(trig_tasks, "_redis", lambda: fake_redis)

    trig_tasks.fire_trigger(trigger_id=trig.id, matched_values={})

    msg = Message.objects.filter(role="user", snapshot_ref=snap).latest("id")
    assert "🧭 What you already know" in msg.content["text"]
    assert msg.content["text"].endswith("SNAP_TEXT")
```

> NOTE for the implementer: if the existing happy-path test patches `ProviderConfig` (for the cost-cap check in `_do_fire`) or uses a different lock-acquire mechanism, copy that setup verbatim into this test so `_do_fire` reaches the user-turn creation. The cost-cap path tolerates a missing `ProviderConfig` (it logs and proceeds), so seeding one is optional; match the existing test for consistency.

- [ ] **Step 2: Run test, verify it fails**

```
docker compose exec web pytest apps/triggers/tests/test_fire_trigger_task.py::test_fire_trigger_injects_coach_when_enabled -v
```

Expected failure: `AssertionError: assert '🧭 What you already know' in 'SNAP_TEXT'` (the fire path posts the bare serialized snapshot; no coach prepended yet).

- [ ] **Step 3: Implement**

In `backend/apps/triggers/tasks.py`, inside `_do_fire`, replace the user-turn creation block (currently):

```python
    user_msg = Message.objects.create(
        thread=thread,
        role="user",
        content={
            "text": serialize_for_ai(
                snap, provider=provider_name, model=trigger.profile.default_model
            )
        },
        snapshot_ref=snap,
        status="done",
    )
```

with (mirroring observer — gating is internal to `assemble_coach_context`, so no extra `enable_coach` branch here, matching `run.py`):

```python
    from apps.threads.coach import assemble_coach_context

    coach = assemble_coach_context(snap, trigger.profile)
    text = serialize_for_ai(
        snap, provider=provider_name, model=trigger.profile.default_model
    )
    user_msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": coach + text},
        snapshot_ref=snap,
        status="done",
    )
```

(Lazy, function-local import of `assemble_coach_context` inside `_do_fire` — `apps.triggers.tasks` already imports many `apps.*` modules at top, but a function-local import here is the conservative choice and matches how the coach is reached elsewhere. `coach` is `""` when disabled / no primary ticker, so `coach + text == text` in the default case — preserving any existing fire test that asserts the exact serialized text.)

- [ ] **Step 4: Run test, verify pass**

```
docker compose exec web pytest apps/triggers/tests/test_fire_trigger_task.py -v
```

Expected: the new test passes AND every pre-existing fire test still passes (coach off / no primary ticker → `coach == ""` → user text unchanged).

- [ ] **Step 5: Commit**

```
git add backend/apps/triggers/tasks.py backend/apps/triggers/tests/test_fire_trigger_task.py && git commit -m "feat(triggers): inject Decision Coach context on the trigger fire path (W8)"
```

---

### Task 5: Coverage map docstring + cross-path regression (W5)

**Files:**
- Modify: `backend/apps/threads/coach.py` (module docstring only — no behavior change)
- Test: `backend/apps/threads/tests/test_coach.py` (RUN: `apps/threads/tests/test_coach.py`)

Verified injection sites (all three funnel through `assemble_coach_context`, which is the single `enable_coach` + `primary_ticker` gate):
1. **Threads** — `apps/threads/views.py` `ThreadViewSet.create` (~line 84): `coach = assemble_coach_context(snap, profile)` prepended to the synthetic pinned-snapshot user `Message`. (NOT `build_system_prompt`, which is the pure system-prompt builder.)
2. **Observer** — `apps/observer/services/run.py:100`: `coach = assemble_coach_context(snap, sched.profile)`; user turn `content={"text": coach + payload_text}`.
3. **Triggers** — `apps/triggers/tasks.py::_do_fire` (Task 4): `coach = assemble_coach_context(snap, trigger.profile)`; user turn `content={"text": coach + text}`.

- [ ] **Step 1: Write the regression test**

Append to `backend/apps/threads/tests/test_coach.py`. This locks the gate: a snapshot with a `primary_ticker` + an open thesis yields a block when `enable_coach=True` and `""` when `False`, proving every site (which all call this one function) honors the flag identically:

```python
@pytest.mark.django_db
def test_w5_coach_gate_parity(coach_profile):
    """W5: assemble_coach_context is the single enable_coach/primary_ticker gate
    that all three injection sites (threads view, observer, trigger) call."""
    Thesis.objects.create(
        title="AI capex", ticker="NVDA", direction="bullish",
        conviction=4, status="open", target_price=210,
    )
    snap = _snap(coach_profile)  # primary_ticker=NVDA

    # enable_coach defaults True for coach_profile -> block present.
    on_out = assemble_coach_context(snap, coach_profile)
    assert "🧭 What you already know" in on_out
    assert "Open theses on NVDA" in on_out

    # Flip the flag -> the same call returns "" (no per-site divergence possible).
    coach_profile.enable_coach = False
    coach_profile.save()
    assert assemble_coach_context(snap, coach_profile) == ""

    # No primary ticker -> "" regardless of flag (the other gate).
    coach_profile.enable_coach = True
    coach_profile.save()
    blank = Snapshot.objects.create(
        profile=coach_profile, status="ready", includes=["quotes"], source="manual"
    )
    assert blank.primary_ticker is None
    assert assemble_coach_context(blank, coach_profile) == ""
```

- [ ] **Step 2: Run test, verify it passes (W5 documents existing behavior)**

```
docker compose exec web pytest apps/threads/tests/test_coach.py::test_w5_coach_gate_parity -v
```

Expected: **passes immediately** after Tasks 2–4 — W5 adds no behavior, it documents and locks the gate. (If it fails, STOP and use superpowers:systematic-debugging — a failure means an injection site diverged from the chokepoint.) Do not weaken any code to manufacture a red bar.

- [ ] **Step 3: Implement (docstring only)**

Extend the existing module docstring at the top of `backend/apps/threads/coach.py` with a verified coverage map. The file currently opens with `"""Decision Coach: a base observational system prompt + an auto-assembled, ... cycle.\n"""`. Append before the closing `"""`:

```
Coverage map (verified 2026-05-30 — keep in sync if you add an AI entry point):

* Threads chat — apps.threads.views.ThreadViewSet.create prepends
  assemble_coach_context(snap, profile) to the synthetic pinned-snapshot user
  Message. (build_system_prompt is the pure SYSTEM-prompt builder; it does NOT
  inject the coach.)
* Observer — apps.observer.services.run.run_observer calls
  assemble_coach_context(snap, sched.profile) and prepends it to the user turn.
* Triggers — apps.triggers.tasks._do_fire does the same.

All three funnel through assemble_coach_context, which is the single place the
enable_coach flag and the primary-ticker guard live — flag/ticker parity is
structural, not duplicated. assemble_coach_context returns "" when the profile is
None / coach-disabled, when there is no primary ticker, or when every sub-section
is empty.
```

(No code/behavior change in this step.)

- [ ] **Step 4: Run test, verify pass**

```
docker compose exec web pytest apps/threads/tests/test_coach.py -v
```

Expected: `test_w5_coach_gate_parity` passes with the full coach suite.

- [ ] **Step 5: Commit**

```
git add backend/apps/threads/coach.py backend/apps/threads/tests/test_coach.py && git commit -m "test(threads): coverage map + cross-path coach gate parity (W5)"
```

---

### Task 6: Verification (full gate)

**Files:** none.

- [ ] **Step 1: Run the affected app suites**

```
docker compose exec web pytest apps/threads apps/triggers apps/recall apps/observer -q
```

Expected: green. Confirm these still pass: `test_coach.py` (all, incl. the updated `test_coach_never_raises_when_a_subsource_throws` patch target), `test_search.py` (incl. existing `test_ticker_filter`), the pre-existing trigger fire test(s), and `apps/observer/tests/test_run_observer.py` (unchanged).

- [ ] **Step 2: Full test + lint gate**

```
make test
make lint
```

Expected: `make test` green (pytest in `web` + vitest in `frontend`). `make lint` green for `ruff`/`ruff format`/frontend eslint+tsc; `ty check .` may emit its usual ~900 advisory `unresolved-attribute` diagnostics on Django `.objects`/FK descriptors — that step is `continue-on-error` in CI and is NOT a gate (per CLAUDE.md). Do not treat a non-zero `ty` as failure.

- [ ] **Step 3: Commit (only if lint auto-formatted anything)**

```
git add -A && git commit -m "chore: ruff format after coach batch (W5-W8)"
```

(Skip if `git status` is clean after the gate.)

---

## Out-of-scope note (do NOT fix in this plan)

`apps/recall/services/search.py` imports `SearchRank` at module top (`from django.contrib.postgres.search import SearchQuery, SearchRank`) and uses it in the FTS branch — that import IS present (no latent NameError; the earlier worry was unfounded). No fix needed; do not touch it.

---

## Self-Review

**Spec coverage (W5–W8):**
- **W6 (semantic recall):** Task 1 adds `related_to_situation(ticker, query, *, k=3, kinds=None) -> list[dict]` wrapping `search()` (semantic → FTS → empty), ticker-scoped + kind-filtered + `k`-bounded, `[]` on empty ticker. Task 2 rewires `coach._recall_block(snapshot, ticker)` to call it with `_situation_query(snap, ticker)` and `kinds=("postmortem","thesis","observation")`, `k=_MAX_RECALL_ITEMS=3`. Same dict-hit shape `_recall_block` already renders; degrades via `search`'s fallbacks + `_safe`. ✔
- **W7 (lessons block):** Task 3 adds `_lessons_block(ticker)` — top-2 `status="done"` + decisive-verdict post-mortems for `thesis__ticker=ticker`, newest-first (`-completed_at`), ≤2 bullets read defensively from `report["lessons"]`/`report["what_missed"]` (free-form JSON), tagged `[verdict, horizon_days d]`. Lazy `from apps.thesis.models import PostMortem` (mirrors `_theses_block`). `_safe`-wrapped + internally defensive; hard cap 2×2; look-ahead-safe (done-only). ✔
- **W8 (coach on triggers):** Task 4 inserts `assemble_coach_context(snap, trigger.profile)` into `_do_fire`, prepended to the serialized user text (`coach + text`), mirroring observer's unconditional call + internal gate. Empty when disabled / no primary ticker. ✔
- **W5 (coverage audit + parity):** Task 5 records the verified 3-site coverage map (threads VIEW, observer, trigger — NOT `build_system_prompt`) as the module docstring and adds `test_w5_coach_gate_parity` asserting the single `assemble_coach_context` chokepoint honors `enable_coach` and the primary-ticker guard. ✔

**Placeholder scan:** No "TBD" / "similar to Task N" / "add error handling" / "write tests for the above". Every step shows complete real code; Task 4's test names the exact collaborators to patch and instructs the implementer to read the existing fire test first (because that file's exact patch targets/fixtures must be reused verbatim, and the channel did not return that file's body during planning).

**Name/type consistency across tasks (all verified against read code):**
- `search(q, *, k=10, kinds=None, ticker=None) -> list[dict]`; hits are dicts (`h["object_id"]`, `h.get("kind")`, `h.get("snippet")`, `h.get("source_created_at")`, `h.get("link")`). **No `SearchHit`.** ✔
- `related_to_situation` defined Task 1 (returns `list[dict]`), imported at coach module top + used Task 2; monkeypatched as `apps.threads.coach.related_to_situation`. ✔
- `RecallDocument`: `kind` (plain-string `KIND_CHOICES`), `object_id`, `tickers` (list, `tickers__contains`), `source_created_at`. **No `RecallDocument.Kind`, no `ticker`, no `source_id`, no `title`.** Test builder `_doc(oid, vec, ...)` reused; extra docs created inline with `object_id=`/`content_hash=`. ✔
- `_recall_block(snapshot, ticker)` (2 args after Task 2); `assemble_coach_context` call site updated to match; header `"### You've noted this before"`. ✔
- `PostMortem`: `thesis` FK, `horizon_days`, `due_at` (**required**, set in every test create), `status` (`"done"`/`"scheduled"` strings), `verdict` (`"correct"/"incorrect"/"inconclusive"` strings), `forward_return_pct`, `report` (free-form JSON), `completed_at` (set via `.update()` since `auto`? no — it's a plain nullable field, so direct create kwarg also works; tests use `.update()` to be explicit). Ticker via `thesis__ticker`. **No `scheduled_for`, no `PostMortem.Status`/`.Verdict` enums.** ✔
- `Thesis`: `direction` `bullish/bearish/neutral`, `status` `open/closed_win/closed_loss/...`, `title`, `ticker` (upper-cased on save). Tests use valid choices. ✔
- `TradingProfile.enable_coach` defaults **True**; `style`, `default_includes`, `default_provider`, `default_model`. ✔
- Triggers: model **`EventTrigger`**; fire path `fire_trigger(trigger_id, matched_values)` → `_do_fire(*, trigger_id, matched_values)`; user turn at `serialize_for_ai(snap, provider=provider_name, model=trigger.profile.default_model)`; `provider_name = trigger.profile.default_provider`. ✔
- Observer mirror: `assemble_coach_context(snap, sched.profile)` unconditional + `content={"text": coach + payload_text}`. ✔
- `build_system_prompt(profile, *, now)` — pure, does NOT take a snapshot, does NOT inject coach (W5 doc corrected accordingly). ✔
- Caps defined before use: `_MAX_RECALL_ITEMS=3`, `_RECALL_QUERY_MAX_CHARS=400`, `_RECALL_KINDS` (Task 2); `_MAX_LESSONS=2`, `_MAX_LESSON_BULLETS=2`, `_LESSON_REPORT_KEYS` (Task 3). ✔

**Never-raise / cycle / parity discipline:** every new coach sub-section runs under `_safe` in `assemble_coach_context`; `_lessons_block` lazy-imports `PostMortem` (function-local, cycle-safe) and is internally defensive about `report`; `related_to_situation` is imported at coach top only from `apps.recall.services.search` (which does not import threads/thesis, so no cycle); `enable_coach`/primary-ticker gating lives solely in `assemble_coach_context`, which all three sites call — no divergent flag logic introduced. ✔
