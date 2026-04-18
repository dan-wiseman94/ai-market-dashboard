# M8 — Polish (Design Spec)

**Milestone tag:** `m8-polish`
**Status:** design approved 2026-04-18
**Depends on:** M7 (event triggers) — shipped and tagged `m7-event-triggers`
**Prior art:** `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` §16 bullet 8

M8 is the final polish milestone of v1. It closes five scope items from the overall design (compare polish, costs dashboard, backups, export, E2E) and two carry-overs flagged explicitly in CLAUDE.md (shared layout / bell-icon relocation from M6; prod `/` 404 fix from M1). The milestone is monolithic in planning and shipping (single plan, single tag) but decomposes internally into seven independent units.

---

## 1. Goals

- Every top-level route sits under a shared chrome (top nav + sidebar + breadcrumbs + keyboard shortcuts); `NotificationBell` moves from `Dashboard.tsx` into the shared layout.
- Prod `/` serves the SPA instead of returning 404.
- Multi-provider compare reports cost per branch + totals in the UI.
- `/costs` grows from "today by provider" into a date-ranged, per-provider + per-model, trend-charted, drill-downable, CSV-exportable dashboard with cost-cap progress bars.
- Nightly pg_dump backups with retention, a `/settings/backups` management UI, `make restore` for destructive restore.
- Async `.zip` exports of everything user-facing (threads, snapshots, observations, trigger firings, profiles, watchlists) with JSON + Markdown + images, plus a per-thread export button.
- Six Playwright-driven E2E journeys covering the major user paths, run against the live compose stack with external services mocked.

## 2. Non-goals

- Mobile layout — desktop-first per §15 YAGNI holds.
- Multi-user auth — notifications stay anonymous; shared layout just gets a stub `<UserMenu/>` linking to Settings.
- Historical backfill of cost data — new aggregations work on existing `AIRun` rows only, no data migration for legacy rows.
- Import (opposite of export). Deferred.
- Observability additions (Sentry/tracing/metrics) — explicitly YAGNI per §15.
- Restore button in the UI — `make restore` only, for blast-radius reasons.
- Auto-rotation of exports — user-managed; warn at 1GB total.

## 3. Work units

Seven independent units, implemented and shipped as one monolithic milestone (one plan doc, one `m8-polish` tag). Internal order drives the plan's step sequence.

| # | Unit | New code location |
|---|---|---|
| 1 | Shared `AppLayout` + keyboard shortcuts | `frontend/src/components/layout/`, `frontend/src/hooks/useKeyboardShortcuts.ts` |
| 2 | Prod `/` 404 fix | `backend/config/settings/prod.py`, `backend/config/urls.py` |
| 3 | Compare cost polish | `apps/threads/tasks.py`, `apps/ai/providers/base.py`, `frontend/src/components/compare/*` |
| 4 | Costs dashboard (rich) | `apps/costs/{views,services,serializers}.py`, `apps/snapshots/models.py` (add `payload_tokens`), `apps/secrets/models.py` (add `monthly_cost_cap_usd`), `frontend/src/routes/costs/*` |
| 5 | Backups | new `apps/backups/*`, `frontend/src/routes/settings/backups/*`, `Makefile` (`restore` target) |
| 6 | Export | new `apps/export/*`, `frontend/src/routes/settings/export/*`, `ThreadDetailPage` button |
| 7 | E2E journeys | new top-level `e2e/` directory, `compose.e2e.yaml`, `Makefile` (`e2e` + `e2e-one` targets) |

Settings page becomes a tabbed parent route hosting Backups and Export sub-pages alongside existing Providers/Secrets/Profiles/Watchlists tabs.

## 4. Unit 1 — Shared `AppLayout`

### 4.1 Component tree

```
<AppLayout>
  <TopNav>
    <LogoLink to="/" />
    <PrimaryNavLinks />          # Dashboard, Snapshot, Threads, Triggers, Schedules, Costs
    <SpacerFlex />
    <ConnectionStatusDot />
    <NotificationBell />
    <UserMenu />                  # stub — links to Settings
  </TopNav>
  <SideNav collapsible>
    <Section title="Trading">Profiles, Watchlists</Section>
    <Section title="System">Settings (with sub-tabs)</Section>
  </SideNav>
  <Breadcrumbs />
  <Outlet />
</AppLayout>
```

### 4.2 Router

`frontend/src/routes.tsx` gets a top-level `<Route element={<AppLayout/>}>` wrapping every existing route. Each route declares `handle.crumb` — either a string or a function `({params, data}) => string` — that the `<Breadcrumbs>` component walks via `useMatches()`.

Pages (Dashboard, Snapshot, Threads, etc.) lose their local page-chrome. Diff is additive on layout files and subtractive on page files. `NotificationBell` stops being imported by `Dashboard.tsx`.

### 4.3 Keyboard shortcuts

`useKeyboardShortcuts()` is a single hook mounted once in `AppLayout`. It listens on `document` and ignores events when `document.activeElement` is an `<input>`, `<textarea>`, or `[contenteditable]`.

| Keys | Destination |
|---|---|
| `g d` | `/` |
| `g s` | `/snapshot` |
| `g t` | `/triggers` |
| `g h` | `/threads` |
| `g c` | `/costs` |
| `g o` | `/schedules` |
| `?` | Open shortcut-help `<Dialog>` |

"g" enters a pending state (300 ms window) where the next character dispatches; any other key cancels. The help dialog lists all bindings, rendered from the same source of truth as the hook.

### 4.4 Sidebar state

Collapsed state persisted under `localStorage["ai-dashboard.sidebar.collapsed"]`. SSR-safe `typeof window !== 'undefined'` guard (kept for hook purity even though the app is SPA-only).

### 4.5 Tests (TDD, all red-first)

- `frontend/src/__tests__/AppLayout.test.tsx` — renders children in `<Outlet/>`; `NotificationBell` present on arbitrary child route; sidebar toggle writes to localStorage.
- `frontend/src/__tests__/keyboardShortcuts.test.tsx` — `g t` navigates; ignored inside an `<input>`; `g <unmapped>` is a no-op.
- `frontend/src/__tests__/breadcrumbs.test.tsx` — static `handle.crumb` renders; function `handle.crumb` receives route params.

## 5. Unit 2 — Prod `/` 404 fix

Combined approach:

1. `backend/config/settings/prod.py` — set `WHITENOISE_INDEX_FILE = True`.
2. `backend/config/urls.py` — append as the **last** pattern:
   ```python
   re_path(
       r"^(?!api/|static/|render/|ws/).*$",
       TemplateView.as_view(template_name="index.html"),
   )
   ```
   `TEMPLATES[0]["DIRS"]` must include the static root in prod (verify Vite prod build emits `index.html` into `STATICFILES_DIRS[0]` during `npm run build`).
3. Deep links (`/threads/123`, `/triggers`, etc.) resolve via the catch-all + client-side router.

### 5.1 Tests

- `backend/apps/core/tests/test_spa_fallback.py` —
  - `GET /` → 200, `Content-Type: text/html`, body starts with `<!doctype html>`.
  - `GET /api/nonexistent` → 404 JSON, not the SPA shell.
  - `GET /static/foo.css` → served by Whitenoise (not intercepted by catch-all).

## 6. Unit 3 — Compare cost polish

### 6.1 `cost` event

Add a new event variant to the provider-stream union consumed by the compare branch channel (`thread.<id>.branch.<msg_id>`). Providers continue to emit `text_delta` / `usage` / `done` / `error` as before; the **task wrapper** `run_ai_on_message` emits an additional `cost` event after the provider's `done`, derived from the `AIRun` row just written.

Event shape:
```json
{
  "event": "cost",
  "cost_usd": "0.0123",
  "tokens_in": 1250,
  "tokens_out": 320,
  "tokens_cached": 800,
  "duration_ms": 1820
}
```
`cost_usd` is a Decimal-as-string for consistency with Django serialization.

### 6.2 Frontend consumption

- `useBranchState(parentMsgId)` reducer hook tracks per-branch `{status, cost, tokensIn, tokensOut, startedAt, completedAt}`. Subscribes to branch channels from `ThreadDetailPage`.
- `BranchTabs.tsx` tab label becomes `<Name> <CostBadge>$X.XXXX</CostBadge>`; badge is a pulsing dot until `cost` event arrives.
- New `<CompareTotalsStrip>` rendered below the tab row:
  ```
  Total: $0.0248 · 3 branches · 1.8s slowest
  ```
  where "slowest" is `max(completedAt - startedAt)` across branches.

### 6.3 Tests

- `backend/apps/threads/tests/test_compare_cost_event.py` — mock provider `done`; task emits `cost` event with correct shape; value matches `AIRun.cost_usd`.
- `backend/apps/threads/tests/test_compare_total_computation.py` — given 3 branches with known fixture usage/pricing, total equals sum, slowest equals max duration.
- `frontend/src/__tests__/BranchTabs.cost.test.tsx` — badge renders `$0.0123` after cost event; spinner before.
- `frontend/src/__tests__/CompareTotals.test.tsx` — totals update incrementally as branches finish.

## 7. Unit 4 — Costs dashboard (rich)

### 7.1 Schema additions

No new tables — aggregations query `AIRun`. Add indexes:
- `AIRun(created_at)`
- `AIRun(thread_id, created_at)`
- `AIRun(provider, model, created_at)`

Field additions:
- `SnapshotSection.payload_tokens: PositiveIntegerField(default=0)` — populated at payload-build time by the existing token-budget estimator; used for per-snapshot drill-down.
- `ProviderConfig.monthly_cost_cap_usd: DecimalField(max_digits=10, decimal_places=4, null=True)` — analog of the existing `daily_cost_cap_usd`.

### 7.2 Endpoints

`apps/costs/views.py` (new alongside the existing `costs_today`):

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/costs/summary?from=<iso>&to=<iso>` | `{total, by_provider[], by_model[], by_thread[], daily[]}` |
| `GET` | `/api/costs/snapshot/<id>` | Per-section token attribution + derived cost share |
| `GET` | `/api/costs/caps` | `{daily: {cap, spent, pct}, monthly: {...}}` |
| `GET` | `/api/costs/export.csv?from=<iso>&to=<iso>` | CSV stream of raw `AIRun` rows in range |

Default range when omitted: last 30 days. Aggregation uses a single `annotate`-based queryset per response.

`/api/costs/today` remains for back-compat; to be removed in a later cleanup.

### 7.3 Service layer

`apps/costs/services.py` gains pure functions:

- `summary(start, end) -> dict` — aggregates `by_provider`, `by_model`, `by_thread` (top N), `daily[]` (date-filled, zero-padded gaps).
- `snapshot_breakdown(snapshot_id) -> list[dict]` — returns per-section `{section, payload_tokens, cost_share_usd}` where `cost_share_usd = (payload_tokens / total_tokens_in) * ai_run.cost_usd`. Honest about the attribution being proportional-to-tokens, not per-API-call.
- `caps() -> dict` — reads `ProviderConfig.{daily,monthly}_cost_cap_usd`, sums `AIRun.cost_usd` within {today, MTD}, returns pct (clamped 0..1 for the bar; raw `spent` in USD preserved for display overshoot).
- `csv_rows(start, end) -> Iterable[list]` — generator for `StreamingHttpResponse`.

### 7.4 Frontend

`/costs` layout (recharts for the line chart):

```
┌─────────────────────────────────────────────────────────┐
│  Costs                              [⇣ Export CSV]      │
│  [Date range: Last 30 days ▾] [From] [To]  [Refresh]    │
├─────────────────────────────────────────────────────────┤
│  Daily cap:  ████████░░░░  $3.20 / $10.00  (32%)        │
│  Monthly:    ██░░░░░░░░░░  $42 / $300     (14%)         │
├─────────────────────────────────────────────────────────┤
│  ╔═══════════════════════════════════════════╗          │
│  ║       Daily cost (line chart)             ║          │
│  ╚═══════════════════════════════════════════╝          │
├──────────────────────┬──────────────────────────────────┤
│  By provider         │  By model                        │
├──────────────────────┴──────────────────────────────────┤
│  Top 10 threads by cost  →  /threads/<id>               │
└─────────────────────────────────────────────────────────┘
```

Date range presets: Today / Last 7 days / Last 30 days / This month / Last month / Custom.

Progress bars turn amber at ≥80%, red at ≥100% of cap. `monthly_cost_cap_usd === null` ⇒ hide the monthly row entirely.

Per-snapshot drill-down: new route `/costs/snapshot/:id` reachable from snapshot detail via "View cost attribution".

### 7.5 CSV

`StreamingHttpResponse` + `csv.writer(Echo())`. Columns: `created_at, provider, model, thread_id, snapshot_id, tokens_in, tokens_out, tokens_cached, cost_usd, duration_ms`. Filename default `ai-dashboard-costs-YYYYMMDD-YYYYMMDD.csv`.

### 7.6 Tests

- `apps/costs/tests/test_summary_aggregation.py` — 20 seeded `AIRun` rows across 3 providers / 4 models / 2 threads; assert each aggregation sum; assert `daily[]` includes zero-rows for gaps in range.
- `apps/costs/tests/test_caps.py` — 0% / 50% / 100% / 120% (overshoot) cases; monthly cap nullable.
- `apps/costs/tests/test_csv_export.py` — header row; streaming response type; filename.
- `apps/costs/tests/test_snapshot_drilldown.py` — section `payload_tokens` sums to `AIRun.tokens_in` within ±1; cost-share fractions sum to `AIRun.cost_usd` within floating-point tolerance.
- `frontend/src/__tests__/CostsPage.test.tsx` — fixture → cap bars, chart, tables all render.
- `frontend/src/__tests__/CostsDateRange.test.tsx` — preset changes update `from`/`to` in the URL query string.

## 8. Unit 5 — Backups

### 8.1 Model

`apps.backups.models.BackupRecord`:

```python
class BackupRecord(models.Model):
    created_at = DateTimeField(auto_now_add=True, db_index=True)
    filename   = CharField(max_length=255, unique=True)   # YYYY-MM-DD-HHMMSS.sql.gz
    size_bytes = BigIntegerField()
    sha256     = CharField(max_length=64)
    kind       = CharField(choices=[("scheduled","scheduled"),("manual","manual")])
    status     = CharField(choices=[("ok","ok"),("failed","failed"),
                                    ("rotated","rotated"),("deleted","deleted"),
                                    ("missing","missing")])
    error      = TextField(blank=True, default="")
```

The row is the source of truth. Files on disk may be removed out-of-band (user, OS rotation); a reconciler run at each beat-task start marks orphan rows as `missing`.

### 8.2 Task

`apps.backups.tasks.run_backup(kind)` — `@shared_task(bind=True, autoretry_for=(), max_retries=0)`.

1. `redis.set("backup:running", "1", nx=True, ex=1800)` — abort if already held.
2. Timestamp → path `/data/backups/<ts>.sql.gz`.
3. `subprocess.run(["pg_dump", "-Fc", "-Z", "6", ...], check=True, timeout=1800)` streamed via stdout redirect to the target path. Credentials come from `$PGHOST`/`$PGUSER`/`$PGPASSWORD`/`$PGDATABASE` env.
4. Streaming sha256 + stat size.
5. Insert `BackupRecord(status="ok", kind=kind, ...)`.
6. Rotation: list `scheduled` records ordered newest-first; for each beyond the keep-count (`BACKUPS_KEEP_SCHEDULED`, default 7), unlink file and set `status="rotated"`. Manual backups never auto-rotate.
7. `notify(kind="backup", severity="info", body="...")` — hooks into the existing M6/M7 notification stack.

Failure path: catch → insert `BackupRecord(status="failed", error=truncated_traceback)`; `notify(..., severity="error")`; release the redis key via `finally`.

### 8.3 Beat schedule

Seeded by data migration (M6/M7 precedent): cron `"30 2 * * *"`. Timezone `BACKUP_BEAT_TIMEZONE` env (default UTC). The migration adds the entry via `django_celery_beat.models.CrontabSchedule` + `PeriodicTask`.

### 8.4 Endpoints

`apps/backups/views.py`:

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/backups/` | List `BackupRecord` rows, paginated newest-first |
| `POST` | `/api/backups/run/` | Enqueue `run_backup.delay(kind="manual")`; 202 with job row |
| `GET` | `/api/backups/<id>/download/` | `FileResponse` streaming `.sql.gz`; `Content-Disposition: attachment` |
| `DELETE` | `/api/backups/<id>/` | Unlink file; row `status` → `deleted` |

### 8.5 Restore (CLI only)

New `Makefile` target:

```makefile
restore:
	@test -n "$(file)" || (echo "usage: make restore file=<name>"; exit 1)
	docker compose stop beat worker
	docker compose exec web pg_restore --clean --if-exists -h $$PGHOST -U $$PGUSER -d $$PGDATABASE /data/backups/$(file)
	docker compose start beat worker
```

Restore is intentionally not an HTTP endpoint nor a UI button. Blast radius is too high.

### 8.6 Frontend

`/settings/backups`:

```
Backups                                [Back up now ↻]
Daily at 02:30 UTC · keep last 7 scheduled
───────────────────────────────────────────────────────
2026-04-18 02:30   24.3 MB   [Download ⇣] [Delete 🗑]
2026-04-17 02:30   23.8 MB   [Download ⇣] [Delete 🗑]
...
2026-04-12 14:05   22.1 MB   manual   [Download]
```

- "Back up now" disables while a run is in-flight (WS `backup.running` from `notify`).
- Failed rows render with an error icon + tooltip of `error`.
- Deleted/rotated rows dimmed, no actions.
- Delete action opens a confirmation `<Dialog>` (scheduled backups can be re-run; manual backups cannot be recovered once removed).

### 8.7 Tests

- `apps/backups/tests/test_run_backup.py` — mock `subprocess.run`; assert full command args; record fields populated; sha256 matches a fixture.
- `apps/backups/tests/test_rotation.py` — 9 scheduled + 2 manual rows; after `run_backup`, exactly 7 scheduled remain `ok` on disk, 2 marked `rotated`, manuals untouched.
- `apps/backups/tests/test_lock.py` — second concurrent invocation raises `Ignore`; first completes.
- `apps/backups/tests/test_reconciler.py` — row with missing file → `status="missing"` at next tick.
- `apps/backups/tests/test_views.py` — list / run-now / download / delete happy paths + 404s.
- `frontend/src/__tests__/BackupsPage.test.tsx` — list renders; Back-up-now disables during run; row actions call correct endpoints.
- Makefile golden-output: `make restore file=missing.sql.gz` → exit 1 with a clear error.

## 9. Unit 6 — Export

### 9.1 Model

`apps.export.models.ExportJob`:

```python
class ExportJob(models.Model):
    created_at   = DateTimeField(auto_now_add=True, db_index=True)
    completed_at = DateTimeField(null=True)
    scope        = JSONField()
    format       = CharField(choices=[("zip","zip")])
    status       = CharField(choices=[("pending","pending"),("running","running"),
                                      ("done","done"),("failed","failed")])
    filename     = CharField(max_length=255, blank=True, default="")
    size_bytes   = BigIntegerField(null=True)
    sha256       = CharField(max_length=64, blank=True, default="")
    error        = TextField(blank=True, default="")
```

Files under `/data/exports/<uuid>.zip`. Same disk-reconciler pattern as backups.

Size warning: when `sum(size_bytes where status='done') > 1 GiB`, frontend shows a banner on `/settings/export` suggesting deletion. No auto-rotation.

### 9.2 Bundle layout

```
ai-dashboard-export-YYYYMMDD-HHMMSS/
  manifest.json                 # {version, generated_at, scopes, counts}
  threads/
    <thread-id>/
      meta.json                 # thread row + messages[] inline
      thread.md                 # rendered chronological transcript
  snapshots/
    <snapshot-id>/
      meta.json                 # snapshot + sections[]
      payload.json              # the AI payload sent
      summary.md                # if AI summary exists
      images/
        chart-<ticker>.png
        screenshot.png
  observations/
    <schedule-id>/
      runs.json
      runs.md
  triggers/
    <trigger-id>/
      config.json               # trigger + DSL
      firings.json
  profiles/profiles.json
  watchlists/watchlists.json
```

Version in `manifest.json` is `1`.

### 9.3 Task

`apps.export.tasks.build_export(job_id)` — `@shared_task(autoretry_for=(), max_retries=0)`.

1. Load job, mark `running`, emit WS `export.running`.
2. Open `zipfile.ZipFile(tempfile, "w", ZIP_DEFLATED)`.
3. Iterate scopes. For each thread/snapshot/etc. in-scope:
   - Call pure serializer (new `apps/export/serializers.py`, not DRF) returning `{path: bytes_or_str}` pairs.
   - Write each entry to the zip as it's produced (no in-memory buffering of the whole bundle).
4. Snapshot images: stream `bytes(SnapshotImage.data)` directly into the zip entry.
5. Close zip; rename to final `/data/exports/<uuid>.zip`.
6. Compute streaming sha256, stat size; mark `done`; emit WS `export.done`.
7. Failure: catch → `status=failed`, truncated traceback; emit WS `export.failed`.

No retries; "Retry" in the UI creates a new `ExportJob`.

### 9.4 Serializers (new, not DRF)

`apps/export/serializers.py` has pure functions per scope:

```python
def thread_to_json(thread: Thread) -> dict: ...
def thread_to_markdown(thread: Thread) -> str: ...
def snapshot_to_json(snapshot: Snapshot) -> dict: ...
def snapshot_to_markdown(snapshot: Snapshot) -> str: ...
def observer_runs_to_json(schedule: ObserverSchedule) -> dict: ...
def observer_runs_to_markdown(schedule: ObserverSchedule) -> str: ...
def trigger_to_json(trigger: EventTrigger) -> dict: ...
def profiles_to_json() -> dict: ...
def watchlists_to_json() -> dict: ...
```

Explicit field selection. Encrypted fields (Schwab tokens, API keys) are **never** traversed; `ProviderConfig` exports `{name, provider, model, daily_cost_cap_usd, monthly_cost_cap_usd}` and nothing secret.

### 9.5 Endpoints

| Method | Path | Action |
|---|---|---|
| `POST` | `/api/export/` | `{scope}`; create + enqueue; 202 |
| `GET` | `/api/export/` | List jobs, newest first |
| `GET` | `/api/export/<id>/` | Single job status (polling fallback; WS is primary) |
| `GET` | `/api/export/<id>/download/` | `FileResponse` zip (only when `status="done"`; else 409) |
| `DELETE` | `/api/export/<id>/` | Unlink; row `status="deleted"` |
| `POST` | `/api/export/thread/<thread_id>/` | Convenience single-thread job |

### 9.6 Frontend

`/settings/export`:

```
Export
Choose what to include:
  [✓] Threads        ( ) All  (○) Select…
  [✓] Snapshots      ( ) All  (○) Select…
  [✓] Observations   [✓] Triggers/Firings
  [✓] Profiles + Watchlists
                            [ Start export ]
───────────────────────────────────────────────────────
Recent exports
  2026-04-18 14:12   running…   ████████░░ (indeterminate)
  2026-04-17 09:00   done  142 MB  [Download] [Delete]
  2026-04-15 11:30   failed       [Retry]
```

- "Start export" disables while any job is `running`.
- 1 GiB banner: `Exports currently occupy 1.2 GB. Consider deleting old ones.`

Per-thread button: `ThreadDetailPage` header gets `[⇣ Export]` → `POST /api/export/thread/<id>/` → toast "Export queued" linking to `/settings/export`.

### 9.7 Tests

- `apps/export/tests/test_serialize_thread.py` — JSON shape; MD rendering; **asserts no encrypted/secret fields appear anywhere**.
- `apps/export/tests/test_serialize_snapshot.py` — payload + images included; images streamed from DB not re-read from disk.
- `apps/export/tests/test_build_export.py` — seed data; assert all expected zip entries present; `manifest.json` counts match; sha256 stable across runs for identical inputs.
- `apps/export/tests/test_scope.py` — partial scopes exclude out-of-scope data.
- `apps/export/tests/test_views.py` — endpoint contracts; download returns 409 before `done`.
- `frontend/src/__tests__/ExportPage.test.tsx` — form submits; job row renders; download button appears on `done`.
- `frontend/src/__tests__/ThreadExportButton.test.tsx` — click → POST → toast with link.

## 10. Unit 7 — E2E journeys

### 10.1 Layout

```
e2e/
  conftest.py
  pages/                    # page object model — one file per route
  journeys/                 # six pytest modules, one per journey
  fixtures/
    seed_minimal.py
    mocks.py
  pyproject.toml            # reuses root pyproject for deps via editable install
```

### 10.2 Six journeys

1. `test_capture_to_cost.py` — `/snapshot` → Capture → WS progress completes → Send to AI → thread streams → `/costs` shows non-zero spend.
2. `test_compare_flow.py` — existing thread → Compare with 2 branches → both stream → both show cost badges → totals strip sums.
3. `test_observer_to_thread.py` — `/schedules` → create with test-only minute interval → run-now → bell notifies → click → observer thread page renders.
4. `test_trigger_firing.py` — `/triggers` → create always-fires trigger → Fire-now → bell notifies → firings tab shows the fire.
5. `test_export_roundtrip.py` — `/settings/export` all scopes → poll to done → download → open zip in tempdir → assert top-level dirs + `manifest.json` → open a thread.md → assert content.
6. `test_backup_roundtrip.py` — `/settings/backups` → Back up now → row `ok` → download → gzip magic bytes + size > 0. Restore tested subprocess-level, not via browser.

### 10.3 Mocks

Compose overlay `compose.e2e.yaml` sets `MOCK_EXTERNAL=true`. Backend routes through `apps/core/mocks.py` when the flag is set:

- Schwab client → deterministic quotes/OHLC/chain/positions.
- Finnhub client → fixed news list.
- AI providers (Claude/OpenAI/Local) → canned token stream + deterministic usage + zero-but-nonzero cost so the `/costs` assertion has something to show.

Auth: test fixture writes `/data/user.token` with a known value before tests run.

### 10.4 Test-only escape hatches

- `OBSERVER_TEST_MIN_INTERVAL_SECONDS` env bypasses the normal minimum-interval validation so Journey 3 doesn't wait real minutes.
- `TRIGGER_TEST_COOLDOWN_SECONDS` env shrinks trigger cooldown for Journey 4 to 1s.

Both env vars read-only in prod builds (assertions in tests ensure they're not set outside `MOCK_EXTERNAL`).

### 10.5 Make targets

```makefile
e2e:
	docker compose -f compose.yaml -f compose.e2e.yaml up -d
	docker compose exec web pytest e2e/ -v
	docker compose -f compose.yaml -f compose.e2e.yaml down

e2e-one:
	docker compose exec web pytest e2e/journeys/$(t).py -v
```

### 10.6 Speed budget

Total ≤5 minutes wall-clock. Per-journey ≤60s. `pytest-xdist` can be added if this drifts; journeys are mostly independent after compose is up.

### 10.7 Tests that test the harness

- `e2e/tests/test_mocks.py` — mock AI returns a canned token stream.
- `e2e/tests/test_fixtures.py` — `seed_minimal` is idempotent.

## 11. Data model summary

| Table / Field | Change |
|---|---|
| `AIRun` | +indexes: `(created_at)`, `(thread_id, created_at)`, `(provider, model, created_at)` |
| `SnapshotSection` | +`payload_tokens: PositiveIntegerField(default=0)` |
| `ProviderConfig` | +`monthly_cost_cap_usd: DecimalField(max_digits=10, decimal_places=4, null=True)` |
| `BackupRecord` | **new** (apps/backups) |
| `ExportJob` | **new** (apps/export) |

All additions are additive migrations — no backfill needed for M8 feature correctness (legacy `AIRun` rows work as-is; `payload_tokens=0` means a legacy snapshot shows proportional-zero attribution, which the UI renders as "—" not "0%").

## 12. WebSocket channels summary

Existing channels (unchanged):
- `user.<id>.notifications`
- `thread.<id>` / `thread.<id>.branch.<msg_id>`
- `snapshot.<id>`

New messages (no new channels):
- `thread.<id>.branch.<msg_id>` now carries a `cost` event (§6.1).
- `user.<id>.notifications` emits `{"kind": "backup", ...}` and `{"kind": "export", ...}` variants.

## 13. Settings page restructure

`/settings` becomes a tabbed parent route:

```
<SettingsLayout>
  <Tabs>
    Providers · Secrets · Profiles · Watchlists · Backups · Export · About
  </Tabs>
  <Outlet />
</SettingsLayout>
```

Pre-existing settings content relocates under its tab (Providers + Secrets pages keep their URLs under `/settings/providers`, `/settings/secrets`). Profiles + Watchlists, currently top-level routes, also get aliased under Settings tabs but their original URLs continue to work (backward-compat for bookmarks).

## 14. Testing strategy

Strict TDD across all units, backend + frontend. Flow per task in the implementation plan:

1. Write failing test(s) — pytest red, vitest red.
2. Write minimum code to make them green.
3. Refactor; assert green.

Every new module has at least one unit test. Integration tests (Celery-eager + `fakeredis`) cover cross-boundary logic (backup rotation, export zip building, cost aggregations). E2E journeys (Unit 7) cover the full user paths against the live compose stack.

CI target `make check` (lint + unit + integration) stays green on every commit. E2E runs via a separate `make e2e` target not gated on every commit (too slow; run before tag).

## 15. Dependencies

- `recharts` (frontend) — new dep; line chart in costs dashboard. Not currently in `frontend/package.json`.
- `pg_dump` / `pg_restore` — already present in the Postgres container; backup task just shells to them.
- Python `zipfile` (stdlib) — export bundling. No new dep.
- No other new deps expected.

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Large exports exceed memory | Stream zip writes per entry; never materialize the whole bundle. |
| Backup clashes with an active snapshot | `redis_lock("backup:running")` only serializes backups with each other; snapshots are read-side and can run concurrently. `pg_dump -Fc` on a running DB is the standard mode. |
| Costs dashboard slow on large `AIRun` tables | Indexes listed in §11; 10k rows/year scale confirms single-query aggregation is fine. Revisit only if row count > 1M. |
| Shortcut `g ?` collision with user typing | Hook ignores events when `activeElement` is editable; 300ms "g pending" window is short. |
| Catch-all URL pattern shadowing a future API path | Negative lookahead (`^(?!api/|static/|render/|ws/)`) covers current namespaces; add new namespace to the pattern when adding new backend route prefixes. |
| Restore deleting the wrong data | Make-only, requires explicit `file=<name>`, stops beat/worker first. No HTTP exposure. |
| E2E tests flaky due to timing | Use Playwright's `expect(...).toBeVisible()` auto-waits; no hard sleeps. Journey 3's minute-interval gets an env escape hatch, not a sleep. |

## 17. Out of scope

- Importing an exported bundle (round-trip restore).
- Observability (metrics, Sentry) — §15 YAGNI.
- Mobile layout — §15 YAGNI.
- Multi-user auth — deferred to post-v1.
- Historical backfill of `SnapshotSection.payload_tokens`.
- Streaming progress for exports (only indeterminate spinner in v1).
- Incremental / differential backups.

## 18. Milestone completion criteria

- `make check` green (backend + frontend + lint).
- `make e2e` green — all six journeys pass in under 5 minutes.
- Every top-level route renders inside `<AppLayout>` with bell + sidebar + breadcrumbs + keyboard shortcuts live.
- Prod `/` returns the SPA shell; deep links work.
- Compare flow shows per-branch cost + totals strip.
- `/costs` shows the full rich dashboard with all components.
- Nightly backup runs (manual verification from beat logs); `/settings/backups` lists it; `make restore` round-trips a known DB state.
- `/settings/export` produces a downloadable zip matching the §9.2 layout; per-thread export button works.
- Tagged `m8-polish`. Carry-over note appended to this spec if anything was intentionally punted in-flight.
