# Snapshot Intelligence (browse · diff · explain) — design

**Date:** 2026-05-28
**Status:** Approved (pending spec review)
**Topic:** Turn snapshots from a write-only fire-and-forget action into a browsable, comparable history with AI-assisted "what changed since last look." Three capabilities on a new `/snapshots` surface: a **history browser** (filterable table + by-ticker timeline), an **arbitrary snapshot-vs-snapshot diff**, and a best-effort **AI explain-diff**. Spec 1 of a three-spec batch (Snapshot Intelligence → Triggers v2 → Semantic Recall).

## Problem

Snapshots are the dashboard's core capture primitive, but once captured they are **write-only from the user's perspective**:

- There is **no list/browse UI** — a captured snapshot is only reachable if you happen to hold its id (via a cost drill-down link). `frontend/src/api/snapshots.ts` has no list fetcher.
- The list endpoint that *does* exist (`SnapshotViewSet`, `apps/snapshots/views.py:22`) serializes **full section payloads** for every row and has no filtering or pagination — unusable as a history list.
- The diff engine (`apps/snapshots/diff.py`) and endpoint (`/api/snapshots/<id>/diff/`) work, but the endpoint **requires `?against=`** (`views.py:71` → 400 without it) and there is **no "find the previous capture" logic** anywhere. So "what changed since last look" — the highest-value question for a daily user who re-captures the same ticker — is not answerable through the product.
- Ticker is not a column; it lives inside the `quotes` section's JSONB payload, so you cannot filter or group captures by ticker.

The diff machinery is built and tested; the gap is **surfacing it** plus the small backend work to make browse/group/prior-selection efficient, and an AI layer that interprets the delta.

## Non-goals (YAGNI)

- **No delete.** Snapshots are referenced by threads (`pinned_snapshot`), theses (`snapshot`), `AIRun`s, `TriggerFiring`s, and messages (`snapshot_ref`); `Snapshot.profile` is `on_delete=PROTECT`. Safe deletion needs its own cascade design — out of scope.
- **No user label/annotation field.** `objective` already names a capture in the browser.
- **No multi-ticker membership.** One derived `primary_ticker` per snapshot; a watchlist capture groups under its first ticker. (Membership-style "every snapshot containing X" is a later enhancement.)
- **No live auto-refresh** of diffs/timeline (manual reload; single-user, low cadence).
- **No new analytics surface** for diffs (the `kind="diff"` threads carry their own `AIRun` cost like any other run).

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Surface shape | Hybrid: filterable table **+** by-ticker timeline | Serves both jobs (manage history / see change-over-time); user-selected |
| Ticker handling | Denormalized `Snapshot.primary_ticker` column + backfill | Ticker lives in related-table JSONB — can't index, paginate, filter or group on it otherwise |
| Prior selection | `previous_snapshot_for(snap)` (same ticker, most-recent prior `ready`); diff endpoint auto-selects it when `against` omitted | One-click "vs last look"; today the endpoint 400s without `against` |
| AI explain transport | Synthetic `done` user `Message` in a `kind="diff"` thread → `run_ai_on_message` | Reuses streaming + cost-tracking + cap-enforcement + capability-warnings verbatim; provider-agnostic; persisted and indexable by Spec 3 (Recall) |
| Diff depth | Extend `diff_sections` to chain/positions/ohlc | Improves both the inline timeline delta and the AI's input; contained + heavily `parametrize`d |
| List performance | New light list serializer (no payloads) + pagination | The current serializer ships full section payloads — unusable for a list |
| Management | Read-only browse in v1 | See non-goals (deletion cascade risk) |

## Architecture

```
 /snapshots page  (table ⇄ by-ticker toggle, filters: profile/ticker/source/date)
        │
        ├── table ──── GET /api/snapshots/?profile=&ticker=&source=&since=&until=   (light serializer, paginated)
        │                    └─ multiselect 2 rows ─┐
        │                                           ▼
        │                              Compare drawer
        │                    GET /api/snapshots/<curr>/diff/?against=<base>  → markdown delta
        │                                           │  [✦ explain with AI]
        ├── by-ticker ─ GET /api/snapshots/timeline/?ticker=NVDA  (ordered + headline_delta_pct)
        │                    └─ node [✦ explain with AI] ─────────┤
        │                                                         ▼
        │                           POST /api/snapshots/<curr>/explain-diff/  body {against?}
        │                              ├─ delta = diff_sections(prev, curr)
        │                              ├─ Thread(kind="diff", profile=curr.profile, pinned_snapshot=curr)
        │                              ├─ Message(role=user, done, snapshot_ref=curr, content={text: framing+delta})
        │                              └─ run_ai_on_message.delay(...)  → streams over thread.<id>
        │                                                         │
        └────────────────────────── navigate to /threads/<thread_id> (live AI synthesis)

 capture pipeline (apps/snapshots/services): after quotes resolve →
        Snapshot.primary_ticker = primary_ticker_from_quotes(quotes_payload)
```

### 1. Model change + shared helper — `apps/snapshots/`

Add one denormalized column to `Snapshot` (`apps/snapshots/models.py`):

```python
primary_ticker = models.CharField(max_length=16, null=True, blank=True, db_index=True)
```

New `apps/snapshots/primary.py`:

```python
def primary_ticker_from_quotes(quotes_payload: dict | None) -> str | None:
    """First ticker key in a quotes section payload, upper-cased; None if absent."""
    if not isinstance(quotes_payload, dict) or not quotes_payload:
        return None
    return str(next(iter(quotes_payload))).upper()


def primary_ticker(snapshot) -> str | None:
    """Derive the primary ticker from a snapshot's stored quotes section."""
    section = snapshot.sections.filter(kind="quotes", status="done").first()
    return primary_ticker_from_quotes(section.payload if section else None)
```

- **Populate at capture:** in the capture flow (`apps/snapshots/services/`), once the `quotes` section is stored, set `snap.primary_ticker = primary_ticker_from_quotes(quotes_payload)` and save (`update_fields=["primary_ticker"]`). Null when no quotes section is requested or it failed.
- **Refactor `apps/analytics/services/leaderboard.py`:** replace its private `_primary_ticker` with an import of `apps.snapshots.primary.primary_ticker` (preserve existing semantics — verify the leaderboard's current "first quotes key" behavior matches; adjust the helper if the leaderboard upper-cases differently). Kills the duplication per the repo's shared-helper convention.

### 2. List endpoint — light serializer + filters + pagination

`SnapshotListSerializer` (`apps/snapshots/serializers.py`), **no payloads**:

```python
{
  "id", "captured_at", "profile_id", "profile_name", "objective", "notes",
  "status", "source", "primary_ticker",
  "section_kinds": ["quotes", "news", ...],          # from prefetched sections
  "section_statuses": {"quotes": "done", "news": "failed", ...},
  "has_image": bool,                                  # images.exists()
  "total_payload_tokens": int,                        # sum(section.payload_tokens)
}
```

`SnapshotViewSet` changes (`apps/snapshots/views.py`):
- `get_serializer_class()` → `SnapshotListSerializer` for `action == "list"`, else the existing `SnapshotSerializer` (retrieve keeps full payloads).
- `get_queryset()` applies query-param filters: `profile` (id), `ticker` (`primary_ticker__iexact`), `source`, `since`/`until` (`captured_at` range). Keeps `prefetch_related("sections")` + `prefetch_related("images")` and `select_related("profile")`.
- `pagination_class = LimitOffsetPagination` (default limit 50) on the viewset (list action only in practice).

### 3. Prior-snapshot selection + diff endpoint relax

New helper (`apps/snapshots/primary.py` or a small `apps/snapshots/history.py`):

```python
def previous_snapshot_for(snap) -> Snapshot | None:
    """Most-recent prior READY snapshot sharing snap.primary_ticker."""
    if not snap.primary_ticker:
        return None
    return (Snapshot.objects
            .filter(primary_ticker=snap.primary_ticker, status="ready",
                    captured_at__lt=snap.captured_at)
            .exclude(id=snap.id)
            .order_by("-captured_at")
            .first())
```

`SnapshotViewSet.diff` (`views.py:63`): when `against` is **omitted**, call `previous_snapshot_for(curr)`; if it returns None, respond `400 {"code": "no_prior"}`. An explicit `against` keeps today's behavior. (This is the only change to existing diff behavior — additive.)

### 4. By-ticker timeline endpoint

```python
@action(detail=False, methods=["get"], url_path="timeline")
def timeline(self, request):
    """GET /api/snapshots/timeline/?ticker=NVDA — ready snapshots for one ticker,
    oldest→newest, each with headline_delta_pct (primary-ticker last % vs the prior node)."""
```

- Loads that ticker's `ready` snapshots (bounded to one ticker) with quotes sections prefetched.
- For each adjacent pair, `headline_delta_pct = (curr_last - prev_last) / prev_last` using the primary ticker's `last` in each quotes payload; `None` when either price is missing. Oldest node has `None`.
- Returns the light serializer fields **plus** `headline_delta_pct` per node.

### 5. Deepen `diff_sections` — `apps/snapshots/diff.py`

Today `_diff_one` only routes quotes/news/breadth. Add three branches (each must tolerate unexpected payload shapes — the diff **never raises**, current invariant preserved via `_as_dict`):

- `_diff_chain(prev, curr)` — for matching expirations/strikes, report notable IV shifts and volume/OI jumps on the largest movers (cap to top N lines); ignore moves below a small IV-delta threshold.
- `_diff_positions(prev, curr)` — per symbol, report P/L and quantity deltas; flag newly opened / closed positions.
- `_diff_ohlc(prev, curr)` — report last/﻿range change for the tracked ticker(s).

Per-section "noise" thresholds live as module constants next to `_NOISE_PCT`. These feed both the inline timeline delta and the AI explain input.

### 6. AI explain-diff endpoint

```python
@action(detail=True, methods=["post"], url_path="explain-diff")
def explain_diff(self, request, pk=None):
    """POST /api/snapshots/<id>/explain-diff/  body {against?: int}
    Returns {thread_id, message_id, delta}. AI synthesis streams over thread.<id>."""
```

Flow (mirrors `apps/observer/services/run.py` per-fire synthetic-message pattern):
1. `curr = get(pk)`; `base = get(body.against)` or `previous_snapshot_for(curr)`; if no base → `400 {"code": "no_prior"}`.
2. `delta = diff_sections(base_sections, curr_sections)` (deterministic; returned in the response so the UI shows it immediately).
3. `thread = Thread.objects.create(kind="diff", profile=curr.profile, pinned_snapshot=curr, title=f"What changed: {curr.primary_ticker or 'snapshot'} #{base.id}→#{curr.id}")`.
4. `msg = Message.objects.create(thread=thread, role="user", status="done", snapshot_ref=curr, content={"text": framing + "\n\n" + delta})` where `framing` instructs: *"Below is a deterministic diff between two market snapshots of {ticker} captured {t_base} → {t_curr}. Explain what materially changed and why it might matter for the objective: '{objective}'. Be concise; lead with the most significant change."*
5. `run_ai_on_message.delay(thread_id=thread.id, user_message_id=msg.id)`.

The snapshot's `profile` drives provider/model (same as observer threads). Cost caps + capability warnings are enforced inside `run_ai_on_message` — **no new AI plumbing.** Degradation: the deterministic `delta` is always in the response even if the AI run is cost-capped / keyless / errors (best-effort layer, never blocks).

### 7. Cross-app touch (choices-only migration)

`threads.Thread.KIND_CHOICES` += `("diff", "Diff")` — a choices-only migration on `apps.threads` (DB `varchar` unchanged). `diff` threads appear in the threads list filterable by kind, like `consult`/`observer`/`briefing`; they are ordinary AI runs for cost purposes and need no analytics special-casing.

### 8. Frontend

- **Route:** `{ path: "snapshots", element: <SnapshotsPage/>, handle: { crumb: "Snapshots" } }` under `<AppLayout>` in `frontend/src/router.tsx`.
- **`SnapshotsPage.tsx`** — header with a **table ⇄ by-ticker** toggle + filter controls (profile, ticker, source, date range; filters lifted to URL query params so views are bookmarkable).
  - **Table view:** rows from `fetchSnapshots(filters)` (captured_at · primary_ticker · objective · profile · source · section chips · status). Checkbox multiselect capped at 2 → **Compare drawer**.
  - **By-ticker view:** ticker selector → `fetchSnapshotTimeline(ticker)` → timeline nodes showing `headline_delta_pct` and a one-line deterministic delta; `[✦ explain with AI]` per node.
  - **Compare drawer:** `fetchSnapshotDiff(currId, baseId)` markdown delta + `[✦ explain with AI]`.
- **Explain action:** `explainDiff(currId, against?)` → `{thread_id}` → navigate to `/threads/<thread_id>` (existing thread detail streams the synthesis over `thread.<id>`).
- **API additions** (`frontend/src/api/snapshots.ts`): `fetchSnapshots(params)`, `fetchSnapshotTimeline(ticker)`, `explainDiff(id, against?)`. `fetchSnapshotDiff` already exists.
- **Navigation gaps fixed:** add **Snapshots** to `SideNav` (the frontend audit found snapshots unreachable from the sidebar), a `go-snapshots` Cmd-K command, and a free `g <x>` shortcut (verify against `useKeyboardShortcuts.ts` — `s` is taken; pick a free letter).
- Built from `Skeleton`/`SkeletonRows`/`EmptyState`; markdown delta rendered with the existing renderer used on `SnapshotCostPage`.

### 9. Testing

- **`test_primary.py`:** `primary_ticker_from_quotes` (first key, upper-case, None on empty/non-dict); `primary_ticker(snapshot)` reads the done quotes section; `previous_snapshot_for` (same ticker, prior ready only, None when no quotes/no prior).
- **`test_diff.py`** (extend): parametrized `_diff_chain`/`_diff_positions`/`_diff_ohlc` incl. added/removed/below-threshold; invariant that any bad payload shape → no raise.
- **`test_views.py`:** list light serializer omits payloads; filters (profile/ticker/source/since/until); pagination; `timeline` ordering + `headline_delta_pct` math (+ None on missing price); `diff` auto-selects prior when `against` omitted (+ `no_prior` 400); `explain-diff` creates a `kind="diff"` thread + done user message + dispatches `run_ai_on_message`, returns delta, and `no_prior` 400.
- **Capture:** `primary_ticker` set after quotes resolve; null when quotes absent/failed.
- **Migration:** backfill data migration populates `primary_ticker` from existing quotes sections and reverses to null.
- **Frontend (`vitest`):** `SnapshotsPage` table/timeline/compare-drawer render (loading/empty/populated); multiselect cap of 2; `explainDiff` navigates to the thread.
- **E2E (`ui` lane):** `e2e/ui/test_snapshots_browse_gold.py` — browse → filter → compare two → explain (assert the diff thread opens and streams under `MOCK_EXTERNAL`).

### 10. Ops & migrations

- `apps/snapshots/migrations/` : (a) `AddField Snapshot.primary_ticker` (nullable, indexed — reversible `RemoveField`); (b) a `RunPython` **backfill** data migration (forward: derive from quotes sections via the app-registry model; reverse: set null) — both reversible, no destructive ops, no table locks of concern at single-user scale.
- `apps/threads/migrations/` : choices-only `AlterField` on `Thread.kind`.
- **No new Celery task or beat entry** — `explain-diff` reuses the existing `run_ai_on_message` task, so **no `worker`/`beat` restart needed**.
- No new dependency, credential, or external service.

## Implementation order (for the plan)

1. `Snapshot.primary_ticker` field + `AddField` migration; `apps/snapshots/primary.py` (`primary_ticker_from_quotes`, `primary_ticker`, `previous_snapshot_for`) + tests.
2. Capture-flow population of `primary_ticker`; backfill data migration; refactor `leaderboard` to import the shared helper.
3. `SnapshotListSerializer` + `SnapshotViewSet` (`get_serializer_class`/`get_queryset`/pagination/filters) + `timeline` action + diff `against`-optional relax + tests.
4. Deepen `diff_sections` (chain/positions/ohlc) + parametrized tests.
5. `Thread.kind` "diff" choices migration; `explain-diff` action + tests.
6. Frontend: API client additions, `SnapshotsPage` (table + timeline + compare drawer), explain→thread navigation, SideNav/Cmd-K/shortcut, with vitest coverage.
7. E2E `test_snapshots_browse_gold.py`.

Steps 3–7 depend only on steps 1–2; step 4 is independent of 3 and can be parallelized; step 5 depends on 3 (shares the viewset) and 4 (uses the deepened delta).
