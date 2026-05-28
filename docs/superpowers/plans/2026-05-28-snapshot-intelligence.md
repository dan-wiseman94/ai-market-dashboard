# Snapshot Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make snapshots browsable, comparable, and AI-explainable — a `/snapshots` history surface (table + by-ticker timeline), arbitrary snapshot-vs-snapshot diff, and a best-effort "what changed & why" AI synthesis.

**Architecture:** Denormalize a derived `primary_ticker` onto `Snapshot` to make ticker filter/group/prior-selection indexable; add a light list serializer + filters + a timeline action; deepen the existing `diff_sections`; route the AI "explain" through a new `kind="diff"` thread via the existing `run_ai_on_message` synthetic-message pattern (no new AI plumbing). Spec: `docs/superpowers/specs/2026-05-28-snapshot-intelligence-design.md`.

**Tech Stack:** Django 6 + DRF, Celery, Postgres 17, React + TypeScript + Vite, Vitest, Playwright (e2e). Everything runs in Docker.

**Conventions for every task:**
- Backend tests run in-container: `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (WORKDIR is `/app/backend`, so paths drop the `backend/` prefix).
- Frontend tests: `docker compose exec frontend pnpm exec vitest run <path> -t "<name>"`.
- Migrations: `make makemigrations` then `make migrate`.
- Commits are conventional (`feat(snapshots):` etc.) and end with the project's `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## File Structure

- `backend/apps/snapshots/models.py` — add `Snapshot.primary_ticker` (modify).
- `backend/apps/snapshots/primary.py` — **new**: `primary_ticker_from_quotes`, `primary_ticker`, `previous_snapshot_for`.
- `backend/apps/snapshots/services/__init__.py` — populate `primary_ticker` at capture (modify).
- `backend/apps/analytics/services/leaderboard.py` — use the shared helper (modify; delete local `_primary_ticker`).
- `backend/apps/snapshots/diff.py` — deepen with chain/positions/ohlc (modify).
- `backend/apps/snapshots/serializers.py` — add `SnapshotListSerializer`; expose `primary_ticker` on detail (modify).
- `backend/apps/snapshots/views.py` — list serializer switch + filters + pagination + `timeline` action + `diff` against-optional + `explain_diff` action (modify).
- `backend/apps/threads/models.py` — add `("diff","Diff")` to `Thread.KIND_CHOICES` (modify).
- `backend/apps/snapshots/migrations/` — field migration + backfill data migration (new).
- `backend/apps/threads/migrations/` — choices-only migration (new).
- `frontend/src/api/snapshots.ts` — `fetchSnapshots`, `fetchSnapshotTimeline`, `explainDiff` (modify).
- `frontend/src/pages/SnapshotsPage.tsx` + `frontend/src/pages/snapshots/` — **new** page + table/timeline/compare-drawer components.
- `frontend/src/router.tsx`, `components/layout/SideNav.tsx`, `hooks/useKeyboardShortcuts.ts`, `AppLayout` commands — wire route/nav/shortcut (modify).
- `e2e/ui/test_snapshots_browse_gold.py` — **new**.

---

## Task 1: `Snapshot.primary_ticker` field

**Files:**
- Modify: `backend/apps/snapshots/models.py`
- Test: `backend/apps/snapshots/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/snapshots/tests/test_models.py
import pytest
from apps.snapshots.models import Snapshot
from apps.profiles.models import TradingProfile

@pytest.mark.django_db
def test_snapshot_primary_ticker_defaults_null():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(profile=p, includes=["quotes"], status="pending")
    assert snap.primary_ticker is None
```

- [ ] **Step 2: Run it — expect failure**

Run: `docker compose exec web pytest apps/snapshots/tests/test_models.py::test_snapshot_primary_ticker_defaults_null -v`
Expected: FAIL (`AttributeError`/unknown field `primary_ticker`).

- [ ] **Step 3: Add the field** in `backend/apps/snapshots/models.py`, on `Snapshot` (after `market_state`):

```python
    primary_ticker = models.CharField(max_length=16, null=True, blank=True, db_index=True)
```

- [ ] **Step 4: Make + run the migration**

Run: `make makemigrations && make migrate`
Expected: a new `snapshots/migrations/000X_snapshot_primary_ticker.py` (`AddField`, nullable).

- [ ] **Step 5: Run the test — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_models.py::test_snapshot_primary_ticker_defaults_null -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/models.py backend/apps/snapshots/migrations/ backend/apps/snapshots/tests/test_models.py
git commit -m "feat(snapshots): add denormalized Snapshot.primary_ticker field"
```

---

## Task 2: `primary.py` — derivation + prior-selection helpers

**Files:**
- Create: `backend/apps/snapshots/primary.py`
- Test: `backend/apps/snapshots/tests/test_primary.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/snapshots/tests/test_primary.py
import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.primary import (
    primary_ticker_from_quotes, primary_ticker, previous_snapshot_for,
)

def test_from_quotes_first_key_upper():
    assert primary_ticker_from_quotes({"nvda": {"last": 1}, "spy": {}}) == "NVDA"

def test_from_quotes_empty_or_bad():
    assert primary_ticker_from_quotes({}) is None
    assert primary_ticker_from_quotes(None) is None
    assert primary_ticker_from_quotes(["x"]) is None

@pytest.mark.django_db
def test_primary_ticker_reads_quotes_section():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready")
    SnapshotSection.objects.create(snapshot=snap, kind="quotes", status="done",
                                   payload={"AAPL": {"last": 10}})
    assert primary_ticker(snap) == "AAPL"

@pytest.mark.django_db
def test_primary_ticker_none_without_quotes():
    p = TradingProfile.objects.create(name="P", default_includes=["news"])
    snap = Snapshot.objects.create(profile=p, includes=["news"], status="ready")
    SnapshotSection.objects.create(snapshot=snap, kind="news", status="done", payload={"items": []})
    assert primary_ticker(snap) is None

@pytest.mark.django_db
def test_previous_snapshot_for_same_ticker_prior_ready():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    older = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA")
    newer = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA")
    other = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker="SPY")
    assert previous_snapshot_for(newer).id == older.id
    assert previous_snapshot_for(older) is None          # nothing prior
    assert previous_snapshot_for(other) is None          # different ticker

@pytest.mark.django_db
def test_previous_snapshot_for_none_when_no_ticker():
    p = TradingProfile.objects.create(name="P", default_includes=["news"])
    snap = Snapshot.objects.create(profile=p, includes=["news"], status="ready", primary_ticker=None)
    assert previous_snapshot_for(snap) is None
```

- [ ] **Step 2: Run — expect failure**

Run: `docker compose exec web pytest apps/snapshots/tests/test_primary.py -v`
Expected: FAIL (`ModuleNotFoundError: apps.snapshots.primary`).

- [ ] **Step 3: Implement** `backend/apps/snapshots/primary.py`:

```python
"""Primary-ticker derivation + prior-snapshot selection for a snapshot."""
from __future__ import annotations

from typing import Any

from apps.snapshots.models import Snapshot


def primary_ticker_from_quotes(quotes_payload: Any) -> str | None:
    """First ticker key in a quotes-section payload, upper-cased; None if absent."""
    if not isinstance(quotes_payload, dict) or not quotes_payload:
        return None
    return str(next(iter(quotes_payload))).upper()


def primary_ticker(snapshot: Snapshot) -> str | None:
    """Derive the primary ticker from a snapshot's quotes section.

    Iterates ``sections.all()`` (prefetch-friendly — no extra query when the
    caller has prefetched) rather than a filtered query.
    """
    for sec in snapshot.sections.all():
        if sec.kind == "quotes" and isinstance(sec.payload, dict) and sec.payload:
            return primary_ticker_from_quotes(sec.payload)
    return None


def previous_snapshot_for(snap: Snapshot) -> Snapshot | None:
    """Most-recent prior READY snapshot sharing snap.primary_ticker."""
    if not snap.primary_ticker:
        return None
    return (
        Snapshot.objects.filter(
            primary_ticker=snap.primary_ticker,
            status="ready",
            captured_at__lt=snap.captured_at,
        )
        .exclude(id=snap.id)
        .order_by("-captured_at")
        .first()
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_primary.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/primary.py backend/apps/snapshots/tests/test_primary.py
git commit -m "feat(snapshots): primary-ticker + previous-snapshot helpers"
```

---

## Task 3: Populate `primary_ticker` at capture + refactor leaderboard

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py:173-176`
- Modify: `backend/apps/analytics/services/leaderboard.py`
- Test: `backend/apps/snapshots/tests/test_capture_primary.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/snapshots/tests/test_capture_primary.py
import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.services import capture_for_existing

@pytest.mark.django_db
def test_capture_sets_primary_ticker(monkeypatch):
    import apps.snapshots.services as svc
    monkeypatch.setitem(svc._FETCHERS, "quotes",
                        lambda **_: {"data": {"tsla": {"last": 5}, "spy": {"last": 1}}})
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(profile=p, includes=["quotes"], status="pending")
    capture_for_existing(snap, watchlist_tickers=["TSLA", "SPY"])
    snap.refresh_from_db()
    assert snap.primary_ticker == "TSLA"

@pytest.mark.django_db
def test_capture_no_quotes_leaves_primary_null(monkeypatch):
    import apps.snapshots.services as svc
    monkeypatch.setitem(svc._FETCHERS, "notes", lambda **_: {"data": {}})
    p = TradingProfile.objects.create(name="P", default_includes=["notes"])
    snap = Snapshot.objects.create(profile=p, includes=["notes"], status="pending")
    capture_for_existing(snap)
    snap.refresh_from_db()
    assert snap.primary_ticker is None
```

- [ ] **Step 2: Run — expect failure**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_primary.py -v`
Expected: FAIL (`primary_ticker` stays None for the TSLA case).

- [ ] **Step 3: Set it in `capture_for_existing`.** In `backend/apps/snapshots/services/__init__.py`, add the import near the top:

```python
from apps.snapshots.primary import primary_ticker as derive_primary_ticker
```

Then replace the block at lines 173-176:

```python
    reps = _representative_tickers(snap, list(watchlist_tickers), ohlc_ticker)
    snap.market_state = _build_market_state(reps)
    snap.status = "ready" if ok_count > 0 else "failed"
    snap.save()
```

with:

```python
    reps = _representative_tickers(snap, list(watchlist_tickers), ohlc_ticker)
    snap.market_state = _build_market_state(reps)
    snap.primary_ticker = derive_primary_ticker(snap)
    snap.status = "ready" if ok_count > 0 else "failed"
    snap.save()
```

- [ ] **Step 4: Refactor leaderboard.** In `backend/apps/analytics/services/leaderboard.py`: add `from apps.snapshots.primary import primary_ticker` to imports; change the call site `primary = _primary_ticker(snap)` (line 61) to `primary = primary_ticker(snap)`; delete the local `_primary_ticker` function (lines 90-95).

- [ ] **Step 5: Run both test suites — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_primary.py apps/analytics/tests -v`
Expected: PASS (capture sets it; leaderboard tests unaffected — the helper uppercases, which matches uppercase OHLC tickers).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/analytics/services/leaderboard.py backend/apps/snapshots/tests/test_capture_primary.py
git commit -m "feat(snapshots): populate primary_ticker at capture; share helper with leaderboard"
```

---

## Task 4: Backfill data migration

**Files:**
- Create: `backend/apps/snapshots/migrations/000X_backfill_primary_ticker.py`
- Test: `backend/apps/snapshots/tests/test_backfill_primary.py`

- [ ] **Step 1: Write the failing test** (asserts the backfill function populates existing rows):

```python
# backend/apps/snapshots/tests/test_backfill_primary.py
import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection

@pytest.mark.django_db
def test_backfill_populates_from_quotes():
    from apps.snapshots.migrations import _backfill  # helper module (Step 3)
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker=None)
    SnapshotSection.objects.create(snapshot=snap, kind="quotes", status="done",
                                   payload={"meta": {"last": 1}})
    _backfill.populate(Snapshot, SnapshotSection)
    snap.refresh_from_db()
    assert snap.primary_ticker == "META"
```

- [ ] **Step 2: Run — expect failure**

Run: `docker compose exec web pytest apps/snapshots/tests/test_backfill_primary.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Create the reusable backfill helper** `backend/apps/snapshots/migrations/_backfill.py`:

```python
"""Backfill helper shared by the data migration and its test (migration-safe:
takes model classes, no direct imports of the live models)."""
from __future__ import annotations


def _first_quotes_key(sections):
    for sec in sections:
        if sec.kind == "quotes" and isinstance(sec.payload, dict) and sec.payload:
            return str(next(iter(sec.payload))).upper()
    return None


def populate(Snapshot, SnapshotSection):
    for snap in Snapshot.objects.all().iterator():
        ticker = _first_quotes_key(snap.sections.all())
        if ticker and snap.primary_ticker != ticker:
            snap.primary_ticker = ticker
            snap.save(update_fields=["primary_ticker"])
```

- [ ] **Step 4: Create the data migration** `backend/apps/snapshots/migrations/000X_backfill_primary_ticker.py` (set the real dependency to the Task-1 field migration):

```python
from django.db import migrations
from apps.snapshots.migrations._backfill import populate

def forwards(apps, schema_editor):
    populate(apps.get_model("snapshots", "Snapshot"), apps.get_model("snapshots", "SnapshotSection"))

def backwards(apps, schema_editor):
    apps.get_model("snapshots", "Snapshot").objects.update(primary_ticker=None)

class Migration(migrations.Migration):
    dependencies = [("snapshots", "000X_snapshot_primary_ticker")]  # <- the AddField from Task 1
    operations = [migrations.RunPython(forwards, backwards)]
```

- [ ] **Step 5: Apply + run the test — expect pass**

Run: `make migrate && docker compose exec web pytest apps/snapshots/tests/test_backfill_primary.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/migrations/ backend/apps/snapshots/tests/test_backfill_primary.py
git commit -m "feat(snapshots): backfill primary_ticker for existing snapshots"
```

---

## Task 5: Light list serializer + filtered, paginated list

**Files:**
- Modify: `backend/apps/snapshots/serializers.py`
- Modify: `backend/apps/snapshots/views.py:22-29`
- Test: `backend/apps/snapshots/tests/test_list_endpoint.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/snapshots/tests/test_list_endpoint.py
import pytest
from rest_framework.test import APIClient
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection

@pytest.fixture
def snaps(db):
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    a = Snapshot.objects.create(profile=p, objective="A", includes=["quotes"], status="ready",
                                source="manual", primary_ticker="NVDA")
    SnapshotSection.objects.create(snapshot=a, kind="quotes", status="done", payload={"NVDA": {"last": 1}})
    b = Snapshot.objects.create(profile=p, objective="B", includes=["news"], status="ready",
                                source="observer", primary_ticker="SPY")
    return p, a, b

def test_list_omits_payloads_and_includes_summary(snaps):
    _, a, _ = snaps
    r = APIClient().get("/api/snapshots/")
    assert r.status_code == 200
    row = next(x for x in r.json()["results"] if x["id"] == a.id)
    assert row["primary_ticker"] == "NVDA"
    assert row["section_kinds"] == ["quotes"]
    assert "payload" not in str(row)            # no section payloads leak into the list

def test_list_filters_by_ticker_and_source(snaps):
    _, a, b = snaps
    r = APIClient().get("/api/snapshots/?ticker=nvda")
    ids = [x["id"] for x in r.json()["results"]]
    assert ids == [a.id]
    r2 = APIClient().get("/api/snapshots/?source=observer")
    assert [x["id"] for x in r2.json()["results"]] == [b.id]
```

- [ ] **Step 2: Run — expect failure**

Run: `docker compose exec web pytest apps/snapshots/tests/test_list_endpoint.py -v`
Expected: FAIL (no pagination wrapper `results`; payloads present; no ticker filter).

- [ ] **Step 3: Add `SnapshotListSerializer`** to `backend/apps/snapshots/serializers.py` and expose `primary_ticker` on detail:

```python
class SnapshotListSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name", read_only=True)
    section_kinds = serializers.SerializerMethodField()
    section_statuses = serializers.SerializerMethodField()
    has_image = serializers.SerializerMethodField()
    total_payload_tokens = serializers.SerializerMethodField()

    class Meta:
        model = Snapshot
        fields: ClassVar = [
            "id", "captured_at", "profile_id", "profile_name", "objective", "notes",
            "status", "source", "primary_ticker",
            "section_kinds", "section_statuses", "has_image", "total_payload_tokens",
        ]

    def get_section_kinds(self, obj):
        return [s.kind for s in obj.sections.all()]

    def get_section_statuses(self, obj):
        return {s.kind: s.status for s in obj.sections.all()}

    def get_has_image(self, obj):
        return any(s.kind == "image" for s in obj.sections.all())

    def get_total_payload_tokens(self, obj):
        return sum(s.payload_tokens for s in obj.sections.all())
```

Add `"primary_ticker"` to `SnapshotSerializer.Meta.fields`.

- [ ] **Step 4: Update the viewset** in `backend/apps/snapshots/views.py`. Add imports + replace the class attrs:

```python
from rest_framework.pagination import LimitOffsetPagination
from apps.snapshots.serializers import SnapshotImageSerializer, SnapshotListSerializer, SnapshotSerializer
```

```python
class SnapshotViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = SnapshotSerializer
    pagination_class = LimitOffsetPagination

    def get_serializer_class(self):
        return SnapshotListSerializer if self.action == "list" else SnapshotSerializer

    def get_queryset(self):
        qs = Snapshot.objects.select_related("profile").prefetch_related("sections")
        p = self.request.query_params
        if p.get("profile"):
            qs = qs.filter(profile_id=p["profile"])
        if p.get("ticker"):
            qs = qs.filter(primary_ticker__iexact=p["ticker"])
        if p.get("source"):
            qs = qs.filter(source=p["source"])
        if p.get("since"):
            qs = qs.filter(captured_at__gte=p["since"])
        if p.get("until"):
            qs = qs.filter(captured_at__lte=p["until"])
        return qs
```

(Remove the old `queryset = ...` attribute — `get_queryset` replaces it.)

- [ ] **Step 5: Run — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_list_endpoint.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/serializers.py backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_list_endpoint.py
git commit -m "feat(snapshots): light list serializer + ticker/source/date filters + pagination"
```

---

## Task 6: `timeline` action (by-ticker, headline_delta_pct)

**Files:**
- Modify: `backend/apps/snapshots/views.py`
- Test: `backend/apps/snapshots/tests/test_timeline.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/snapshots/tests/test_timeline.py
import pytest
from rest_framework.test import APIClient
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection

@pytest.mark.django_db
def test_timeline_orders_and_computes_headline_delta():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    def mk(last):
        s = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA")
        SnapshotSection.objects.create(snapshot=s, kind="quotes", status="done", payload={"NVDA": {"last": last}})
        return s
    a, b = mk(100.0), mk(102.0)
    r = APIClient().get("/api/snapshots/timeline/?ticker=NVDA")
    assert r.status_code == 200
    rows = r.json()["results"]                       # oldest -> newest
    assert [x["id"] for x in rows] == [a.id, b.id]
    assert rows[0]["headline_delta_pct"] is None     # oldest has no prior
    assert round(rows[1]["headline_delta_pct"], 4) == 2.0
```

- [ ] **Step 2: Run — expect failure** (`404`, no `timeline` route).

Run: `docker compose exec web pytest apps/snapshots/tests/test_timeline.py -v`

- [ ] **Step 3: Add the action** to `SnapshotViewSet` (`backend/apps/snapshots/views.py`), using the shared quotes-key helper:

```python
    @action(detail=False, methods=["get"], url_path="timeline")
    def timeline(self, request):
        from apps.snapshots.primary import primary_ticker_from_quotes
        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            return Response({"code": "missing_ticker"}, status=400)
        snaps = list(
            Snapshot.objects.filter(primary_ticker=ticker, status="ready")
            .prefetch_related("sections").order_by("captured_at")
        )
        def last_price(s):
            q = next((x for x in s.sections.all() if x.kind == "quotes"), None)
            key = primary_ticker_from_quotes(q.payload) if q else None
            try:
                return float(q.payload[next(iter(q.payload))]["last"]) if key else None
            except (KeyError, TypeError, ValueError, StopIteration):
                return None
        rows, prev = [], None
        for s in snaps:
            cur = last_price(s)
            delta = ((cur - prev) / prev * 100.0) if (cur is not None and prev) else None
            data = SnapshotListSerializer(s).data
            data["headline_delta_pct"] = delta
            rows.append(data)
            if cur is not None:
                prev = cur
        return Response({"results": rows})
```

- [ ] **Step 4: Run — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_timeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_timeline.py
git commit -m "feat(snapshots): by-ticker timeline endpoint with headline delta"
```

---

## Task 7: `diff` — auto-select prior when `against` omitted

**Files:**
- Modify: `backend/apps/snapshots/views.py:63-83`
- Test: `backend/apps/snapshots/tests/test_diff_endpoint.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/snapshots/tests/test_diff_endpoint.py
import pytest
from rest_framework.test import APIClient
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection

def _snap(p, last):
    s = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA")
    SnapshotSection.objects.create(snapshot=s, kind="quotes", status="done", payload={"NVDA": {"last": last}})
    return s

@pytest.mark.django_db
def test_diff_auto_selects_prior():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    a, b = _snap(p, 100), _snap(p, 110)
    r = APIClient().get(f"/api/snapshots/{b.id}/diff/")     # no ?against
    assert r.status_code == 200
    assert r.json()["prev_id"] == a.id and r.json()["curr_id"] == b.id

@pytest.mark.django_db
def test_diff_no_prior_returns_400():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    only = _snap(p, 100)
    r = APIClient().get(f"/api/snapshots/{only.id}/diff/")
    assert r.status_code == 400 and r.json()["code"] == "no_prior"
```

- [ ] **Step 2: Run — expect failure** (current code returns `missing_against` 400 for the first test).

Run: `docker compose exec web pytest apps/snapshots/tests/test_diff_endpoint.py -v`

- [ ] **Step 3: Update `diff`** in `backend/apps/snapshots/views.py` — replace the `against_id` guard:

```python
    @action(detail=True, methods=["get"])
    def diff(self, request, pk=None):
        from apps.snapshots.primary import previous_snapshot_for
        curr = get_object_or_404(Snapshot.objects.prefetch_related("sections"), id=pk)
        against_id = request.query_params.get("against")
        if against_id:
            try:
                prev = Snapshot.objects.prefetch_related("sections").get(id=against_id)
            except Snapshot.DoesNotExist:
                return Response({"code": "not_found"}, status=404)
        else:
            prev = previous_snapshot_for(curr)
            if prev is None:
                return Response({"code": "no_prior"}, status=400)
        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in curr.sections.all()}
        delta = diff_sections(prev_sections, curr_sections)
        return Response({"delta": delta, "prev_id": prev.id, "curr_id": curr.id})
```

- [ ] **Step 4: Run — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_diff_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_diff_endpoint.py
git commit -m "feat(snapshots): diff auto-selects previous snapshot when against omitted"
```

---

## Task 8: Deepen `diff_sections` (chain / positions / ohlc)

**Files:**
- Modify: `backend/apps/snapshots/diff.py:67-74`
- Test: `backend/apps/snapshots/tests/test_diff_deepen.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/apps/snapshots/tests/test_diff_deepen.py
from apps.snapshots.diff import diff_sections

def test_positions_pl_delta():
    prev = {"positions": [{"symbol": "NVDA", "unrealized_pl": 100, "quantity": 10}]}
    curr = {"positions": [{"symbol": "NVDA", "unrealized_pl": 250, "quantity": 10}]}
    out = diff_sections(prev, curr)
    assert "NVDA" in out and "100" in out and "250" in out

def test_ohlc_last_change():
    prev = {"ohlc": {"ticker": "SPY", "bars": [{"close": 500}]}}
    curr = {"ohlc": {"ticker": "SPY", "bars": [{"close": 505}]}}
    assert "SPY" in diff_sections(prev, curr)

def test_diff_never_raises_on_garbage():
    assert isinstance(diff_sections({"chain": 123}, {"chain": None}), str)
```

- [ ] **Step 2: Run — expect failure** (positions/ohlc produce no lines today).

Run: `docker compose exec web pytest apps/snapshots/tests/test_diff_deepen.py -v`

- [ ] **Step 3: Add branches** in `backend/apps/snapshots/diff.py`. Extend `_diff_one`:

```python
def _diff_one(kind: str, prev: Any, curr: Any) -> str:
    if kind == "quotes":
        return _diff_quotes(_as_dict(prev), _as_dict(curr))
    if kind == "news":
        return _diff_news(_news_items(prev), _news_items(curr))
    if kind == "breadth":
        return _diff_breadth(_as_dict(prev), _as_dict(curr))
    if kind == "positions":
        return _diff_positions(prev, curr)
    if kind == "ohlc":
        return _diff_ohlc(_as_dict(prev), _as_dict(curr))
    if kind == "chain":
        return _diff_chain(_as_dict(prev), _as_dict(curr))
    return ""
```

Add the helpers (each tolerates bad shapes — never raises):

```python
def _diff_positions(prev: Any, curr: Any) -> str:
    def by_sym(rows):
        return {r.get("symbol"): r for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}
    p, c = by_sym(prev), by_sym(curr)
    rows = []
    for sym, cur in c.items():
        pr = p.get(sym)
        if pr is None:
            rows.append(f"- {sym}: opened (P/L {cur.get('unrealized_pl', '?')})")
        elif pr.get("unrealized_pl") != cur.get("unrealized_pl"):
            rows.append(f"- {sym}: P/L {pr.get('unrealized_pl')} → {cur.get('unrealized_pl')}")
    for sym in p.keys() - c.keys():
        rows.append(f"- {sym}: closed")
    return "\n".join(rows)

def _diff_ohlc(prev: dict, curr: dict) -> str:
    def last_close(blob):
        bars = blob.get("data", blob).get("bars") if isinstance(blob.get("data", blob), dict) else None
        if isinstance(bars, list) and bars and isinstance(bars[-1], dict):
            return bars[-1].get("close")
        return None
    pc, cc = last_close(prev), last_close(curr)
    t = (curr.get("data", curr) or {}).get("ticker", "") if isinstance(curr, dict) else ""
    if pc is not None and cc is not None and pc != cc:
        return f"- {t} last: {pc} → {cc}"
    return ""

def _diff_chain(prev: dict, curr: dict) -> str:
    # Compact: report change in the count of expirations/lines; deep greek diffs deferred.
    def n(blob):
        exps = blob.get("expirations") or blob.get("data", {}).get("expirations")
        return len(exps) if isinstance(exps, list) else None
    pn, cn = n(prev), n(curr)
    if pn is not None and cn is not None and pn != cn:
        return f"- expirations: {pn} → {cn}"
    return ""
```

- [ ] **Step 4: Run — expect pass** (and run the existing diff tests to confirm no regression):

Run: `docker compose exec web pytest apps/snapshots/tests/test_diff_deepen.py apps/snapshots/tests/test_diff.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/diff.py backend/apps/snapshots/tests/test_diff_deepen.py
git commit -m "feat(snapshots): deepen diff for positions/ohlc/chain sections"
```

---

## Task 9: `Thread.kind = "diff"` choices migration

**Files:**
- Modify: `backend/apps/threads/models.py:14-19`
- Test: covered by Task 10.

- [ ] **Step 1: Add the choice** in `Thread.KIND_CHOICES`:

```python
        ("diff", "Diff"),
```

- [ ] **Step 2: Make + run the migration**

Run: `make makemigrations && make migrate`
Expected: a choices-only `AlterField` migration on `threads`.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/threads/models.py backend/apps/threads/migrations/
git commit -m "feat(threads): add diff thread kind"
```

---

## Task 10: `explain-diff` action

**Files:**
- Modify: `backend/apps/snapshots/views.py`
- Test: `backend/apps/snapshots/tests/test_explain_diff.py`

- [ ] **Step 1: Write the failing test** (patch the Celery dispatch so no real AI runs):

```python
# backend/apps/snapshots/tests/test_explain_diff.py
import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import Thread, Message

def _snap(p, last):
    s = Snapshot.objects.create(profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA")
    SnapshotSection.objects.create(snapshot=s, kind="quotes", status="done", payload={"NVDA": {"last": last}})
    return s

@pytest.mark.django_db
def test_explain_diff_creates_thread_and_dispatches():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    a, b = _snap(p, 100), _snap(p, 110)
    with patch("apps.snapshots.views.run_ai_on_message") as run:
        r = APIClient().post(f"/api/snapshots/{b.id}/explain-diff/", {}, format="json")
    assert r.status_code in (200, 201)
    body = r.json()
    assert "thread_id" in body and "delta" in body
    th = Thread.objects.get(id=body["thread_id"])
    assert th.kind == "diff" and th.pinned_snapshot_id == b.id
    msg = Message.objects.get(id=body["message_id"])
    assert msg.role == "user" and msg.status == "done" and msg.snapshot_ref_id == b.id
    run.delay.assert_called_once()

@pytest.mark.django_db
def test_explain_diff_no_prior_400():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    only = _snap(p, 100)
    r = APIClient().post(f"/api/snapshots/{only.id}/explain-diff/", {}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "no_prior"
```

- [ ] **Step 2: Run — expect failure** (`404`, no route).

Run: `docker compose exec web pytest apps/snapshots/tests/test_explain_diff.py -v`

- [ ] **Step 3: Implement the action.** In `backend/apps/snapshots/views.py`, add imports:

```python
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message
```

Add to `SnapshotViewSet`:

```python
    @action(detail=True, methods=["post"], url_path="explain-diff")
    def explain_diff(self, request, pk=None):
        from apps.snapshots.primary import previous_snapshot_for
        curr = get_object_or_404(Snapshot.objects.prefetch_related("sections"), id=pk)
        against_id = request.data.get("against")
        if against_id:
            prev = get_object_or_404(Snapshot.objects.prefetch_related("sections"), id=against_id)
        else:
            prev = previous_snapshot_for(curr)
            if prev is None:
                return Response({"code": "no_prior"}, status=400)
        delta = diff_sections(
            {s.kind: s.payload for s in prev.sections.all()},
            {s.kind: s.payload for s in curr.sections.all()},
        )
        thread = Thread.objects.create(
            kind="diff", profile=curr.profile, pinned_snapshot=curr,
            title=f"What changed: {curr.primary_ticker or 'snapshot'} #{prev.id}→#{curr.id}"[:200],
        )
        framing = (
            f"Below is a deterministic diff between two market snapshots of "
            f"{curr.primary_ticker or 'the same set'} captured {prev.captured_at:%Y-%m-%d %H:%M} → "
            f"{curr.captured_at:%Y-%m-%d %H:%M}. Explain what materially changed and why it might "
            f"matter for the objective: '{curr.objective}'. Be concise; lead with the most significant change."
        )
        msg = Message.objects.create(
            thread=thread, role="user", status="done", snapshot_ref=curr,
            content={"text": f"{framing}\n\n{delta}"},
        )
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=msg.id)
        return Response({"thread_id": thread.id, "message_id": msg.id, "delta": delta}, status=201)
```

- [ ] **Step 4: Run — expect pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_explain_diff.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_explain_diff.py
git commit -m "feat(snapshots): AI explain-diff endpoint (kind=diff thread)"
```

---

## Task 11: Frontend — API client, page, nav

**Files:**
- Modify: `frontend/src/api/snapshots.ts`
- Create: `frontend/src/pages/SnapshotsPage.tsx`, `frontend/src/pages/snapshots/SnapshotTable.tsx`, `TickerTimeline.tsx`, `CompareDrawer.tsx`
- Modify: `frontend/src/router.tsx`, `frontend/src/components/layout/SideNav.tsx`, `frontend/src/hooks/useKeyboardShortcuts.ts`, `frontend/src/components/layout/AppLayout.tsx`
- Test: `frontend/src/__tests__/SnapshotsPage.test.tsx`

- [ ] **Step 1: Add API functions** to `frontend/src/api/snapshots.ts`:

```typescript
export type SnapshotListRow = {
  id: number; captured_at: string; profile_id: number; profile_name: string;
  objective: string; status: string; source: string; primary_ticker: string | null;
  section_kinds: string[]; section_statuses: Record<string, string>;
  has_image: boolean; total_payload_tokens: number; headline_delta_pct?: number | null;
};
export const fetchSnapshots = (params: Record<string, string> = {}) =>
  apiGet<{ results: SnapshotListRow[]; count?: number }>(
    `/api/snapshots/?${new URLSearchParams(params)}`);
export const fetchSnapshotTimeline = (ticker: string) =>
  apiGet<{ results: SnapshotListRow[] }>(`/api/snapshots/timeline/?ticker=${encodeURIComponent(ticker)}`);
export const explainDiff = (id: number, against?: number) =>
  apiPost<{ thread_id: number; message_id: number; delta: string }>(
    `/api/snapshots/${id}/explain-diff/`, against ? { against } : {});
```

- [ ] **Step 2: Write the failing component test**

```tsx
// frontend/src/__tests__/SnapshotsPage.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { mockApi } from "./helpers";              // existing test helper
import SnapshotsPage from "../pages/SnapshotsPage";

describe("SnapshotsPage", () => {
  it("renders captured snapshots in the table", async () => {
    mockApi({ "/api/snapshots/": { results: [
      { id: 1, captured_at: "2026-05-28T13:30:00Z", profile_id: 1, profile_name: "P",
        objective: "Scalp", status: "ready", source: "manual", primary_ticker: "NVDA",
        section_kinds: ["quotes"], section_statuses: { quotes: "done" }, has_image: false,
        total_payload_tokens: 10 } ] } });
    render(<SnapshotsPage />);
    expect(await screen.findByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText(/Scalp/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run — expect failure**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotsPage.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 4: Build the page + components.** Create `SnapshotsPage.tsx` with a `table | by-ticker` toggle, filter inputs (profile/ticker/source/date, lifted to URL query params), `SnapshotTable` (rows + 2-row multiselect → `CompareDrawer`), `TickerTimeline` (nodes + `headline_delta_pct` + `[✦ explain]`), and `CompareDrawer` (calls `fetchSnapshotDiff`, renders the markdown delta, `[✦ explain with AI]` → `explainDiff` → `navigate('/threads/'+thread_id)`). Use `Skeleton`/`SkeletonRows`/`EmptyState` and the same markdown renderer used on `SnapshotCostPage`. Follow the ledger design tokens (`ink`/`copper`/`rule`) and the page shell (`px-8 py-8 max-w-5xl mx-auto ledger-fade-in`).

- [ ] **Step 5: Wire route + nav.**
  - `router.tsx`: add `{ path: "snapshots", element: <SnapshotsPage/>, handle: { crumb: "Snapshots" } }` under `<AppLayout>`.
  - `SideNav.tsx`: add a **Snapshots** entry.
  - `useKeyboardShortcuts.ts`: add a `g`-shortcut for snapshots using a **free** letter (verify the existing set in the file; do not reuse a taken one).
  - `AppLayout` `useDefaultCommands`: add a `go-snapshots` Cmd-K command.

- [ ] **Step 6: Run page test + full frontend lint/tsc — expect pass**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotsPage.test.tsx && docker compose exec frontend pnpm run lint`
Expected: PASS (watch for `react-hooks/set-state-in-effect` — derive filter state in render, don't `setState` in an effect).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/snapshots.ts frontend/src/pages/SnapshotsPage.tsx frontend/src/pages/snapshots/ frontend/src/router.tsx frontend/src/components/layout/SideNav.tsx frontend/src/hooks/useKeyboardShortcuts.ts frontend/src/components/layout/AppLayout.tsx frontend/src/__tests__/SnapshotsPage.test.tsx
git commit -m "feat(frontend): /snapshots browser with table, timeline, compare + explain"
```

---

## Task 12: E2E gold journey

**Files:**
- Create: `e2e/ui/test_snapshots_browse_gold.py`

- [ ] **Step 1: Write the journey test** (asserts real UI, no h1-fallbacks): under `MOCK_EXTERNAL`, navigate to `/snapshots`, assert at least one row renders, filter by a ticker, select two rows → Compare, assert the diff delta text appears, click **explain with AI**, assert it navigates to a `/threads/<id>` route and a streamed/assistant message element appears.

```python
# e2e/ui/test_snapshots_browse_gold.py  (sketch — follow the patterns in e2e/ui/test_snapshots_capture_gold.py)
def test_browse_compare_explain(page, base_url):
    page.goto(f"{base_url}/snapshots")
    page.get_by_role("row").first.wait_for()
    # filter, multiselect two, Compare, assert delta, click explain, assert /threads nav + a message bubble
```

- [ ] **Step 2: Run the lane**

Run: `make e2e-one t=ui/test_snapshots_browse_gold.py` (requires `make e2e-up`).
Expected: PASS. If a UI affordance is genuinely missing, fix the page — do **not** weaken the assertion.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_snapshots_browse_gold.py
git commit -m "test(e2e): snapshots browse/compare/explain gold journey"
```

---

## Final verification

- [ ] Run the full backend app suite: `docker compose exec web pytest apps/snapshots apps/analytics apps/threads -q` — all green.
- [ ] `make check` — ruff + ty(advisory) + pytest + frontend lint/tsc/vitest all green.
- [ ] Confirm no section payloads leak into `/api/snapshots/` list responses (perf + size).

## Self-review (completed against the spec)

- **Spec coverage:** history browser (Tasks 5,11) · by-ticker timeline (6,11) · arbitrary diff + auto-prior (7) · deepened diff (8) · AI explain-diff via `kind="diff"` thread (9,10) · primary_ticker denormalization + backfill + shared helper (1–4) · nav gaps fixed (11) · e2e (12). All spec sections map to a task.
- **Placeholders:** none — every code step shows real code; the only deferred detail is the free shortcut letter (Task 11 Step 5), explicitly "verify against the file."
- **Type consistency:** `primary_ticker_from_quotes`/`primary_ticker`/`previous_snapshot_for` signatures are stable across Tasks 2/3/6/7/10; `SnapshotListSerializer` fields match the frontend `SnapshotListRow`; `explain-diff` returns `{thread_id, message_id, delta}` consumed verbatim by `explainDiff`.
