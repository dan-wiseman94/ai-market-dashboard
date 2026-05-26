# M11 — Second Brain (Design Spec)

**Status:** implemented 2026-05-25
**Depends on:** M10/M12 (shipped)
**Prior art:** `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` §16 bullet 11
**Plan:** `docs/superpowers/plans/2026-05-25-m11-second-brain.md`

M11 closes the decision loop. Through M10 the system records what the market looked like and what the AI thought, but never captures what the user decided or whether the AI call was right. M11 adds the missing "decide → review" half: Thesis objects, a decision journal, a post-mortem scheduler, and agent presets that pre-fill capture objectives.

---

## 1. Goals

- Let users record a named directional call (a **Thesis**) against a ticker, with entry/target/invalidation prices, conviction level, and optional FK links to the originating thread and snapshot.
- **Close the loop deterministically**: at each configured horizon (7/30/90 days) compute the actual forward return from stored `OHLCBar` data and assign an objective verdict — correct, incorrect, mixed, or inconclusive — with no AI required.
- **Best-effort AI narrative**: if a Claude key and caps allow, generate a structured post-mortem report (what worked, what was missed, lessons, would-you-repeat, narrative verdict) via `run_structured`; post it as an assistant `Message` into a per-thesis review thread. Gracefully degrade to `report={}` on any non-claude provider, missing key, cap hit, or provider error — the objective verdict always persists.
- Capture **decision-journal entries** on threads so users can record what they actually did (acted/passed/watching/hedged) and why, with optional FK to a thesis.
- Seed four built-in **agent presets** (`earnings-prep`, `devils-advocate`, `pre-trade-bias-check`, `triage-pass`) that pre-fill the snapshot composer's objective text and section includes.

## 2. Non-goals

- Post-mortem for non-Claude providers (best-effort path is Claude-only; OpenAI/Local produce `report={}` silently).
- Multi-user thesis sharing — all thesis/journal data is single-user, matching the rest of the system.
- Broker write path — M11 records decisions but never places or modifies orders.
- Custom horizon configuration per thesis — horizons are global (`THESIS_POSTMORTEM_HORIZONS`).

## 3. Phase 0 — Shared forward-return helper

**New file:** `apps/market/returns.py`

Extracts `nearest_bar_close`, `forward_return_pct`, and `price_path_summary` from `apps/analytics/services/leaderboard.py` (which now imports them). These functions query `OHLCBar` with a ±1h grace window and return `float | None` so callers are explicit about missing-data cases.

`apps/analytics/services/leaderboard.py` is updated to import from `apps.market.returns` rather than redefining the helpers inline.

## 4. Phase 1 — Thesis core (`apps.thesis`)

**New Django app** (`name="apps.thesis"`, `label="thesis"`, served under `/api/`).

### Models

**`Thesis`** — title, ticker (uppercased in `save()`), direction (`bullish|bearish|neutral`), rationale, conviction (1–5, `MinValueValidator`/`MaxValueValidator`), entry/target/invalidation prices (optional), `horizon_days` (default 30), status (`open|closed_win|closed_loss|closed_scratch|invalidated`). FK to `profiles.TradingProfile`, `threads.Thread` (source thread), `snapshots.Snapshot`, and `threads.Thread` again as `review_thread` (the per-thesis review channel) — all `SET_NULL`. `opened_at` (default `now`), `closed_at` (null), `close_note`.

**`PostMortem`** — FK to `Thesis` (`related_name="postmortems"`), `horizon_days`, `due_at`, status (`scheduled|running|done|failed|skipped`), `forward_return_pct` (float, null), verdict (`correct|incorrect|mixed|inconclusive`), `report` (JSONField, default `{}`), FK to `Message` (the review thread message, null). `UniqueConstraint(thesis, horizon_days)` prevents duplicate horizons per thesis.

**`DecisionJournalEntry`** — FK to `threads.Thread` (CASCADE), optional FK to `Thesis` and `snapshots.Snapshot` (both SET_NULL), decision (`acted|passed|watching|hedged`), note. Lives in `apps.thesis` (not `apps.threads`) to avoid a threads→thesis import cycle.

### Endpoints

| Method | Path | Notes |
|---|---|---|
| CRUD | `/api/theses/` | `ThesisViewSet`; `create()` accepts `thread_id`/`snapshot_id`, defaults `entry_price` from snapshot `quotes` section, calls `schedule_postmortems` |
| `POST` | `/api/theses/<id>/close/` | Sets status, `closed_at`, `close_note`; read-only on serializer |
| `POST` | `/api/theses/<id>/run-postmortem/` | Triggers `run_postmortem_task.delay` for any scheduled PostMortems |
| CRUD | `/api/journal/` | `JournalEntryViewSet`; list filtered by `?thread=<id>` |

### Frontend

`api/thesis.ts` + `useTheses` hook + `ThesisBadges` (status/verdict chips). `ThesesPage` at `/theses` (open/closed groups). `ThesisDetailPage` at `/theses/:id` (fields, Close control, post-mortem cards with Run-now button). SideNav "Theses" entry. `g j` keyboard shortcut. `go-theses` Cmd-K command.

## 5. Phase 2 — Post-mortem scheduler + AI replay

### `apps/thesis/services/postmortem.py`

**`schedule_postmortems(thesis)`** — idempotent; calls `PostMortem.objects.get_or_create(thesis, horizon_days, ...)` once per entry in `settings.THESIS_POSTMORTEM_HORIZONS` (`[7, 30, 90]`).

**`objective_verdict(thesis, fwd_pct)`** — deterministic; no AI. DEADZONE = 1.0%:
- `fwd_pct is None` → `"inconclusive"`
- direction `neutral`: correct if `|fwd_pct| <= DEADZONE`, else incorrect
- direction `bullish`: correct if `fwd_pct >= DEADZONE`, incorrect if `fwd_pct <= -DEADZONE`, else mixed
- direction `bearish`: correct if `fwd_pct <= -DEADZONE`, incorrect if `fwd_pct >= DEADZONE`, else mixed

**`run_postmortem(pm_id)`** — the two load-bearing design choices are here:

1. **Idempotent atomic claim.** `PostMortem.objects.filter(id=pm_id, status="scheduled").update(status="running")` returns 0 if the row is already running/done/failed/skipped — the function exits immediately. This means a beat re-tick, a run-now+beat overlap, or repeated run-now clicks each try to claim the same row; exactly one succeeds and runs the AI; the rest are no-ops. No double-billing.

2. **Graceful AI degradation.** After computing `fwd_pct` + `price_path_summary` and calling `objective_verdict` (which always succeeds), the function wraps `_attempt_ai_narrative(pm, thesis, fwd, path)` in a bare `except Exception` that logs and sets `pm.report = {}`. The objective verdict + forward return + `status="done"` are saved regardless. `_attempt_ai_narrative` itself returns early (never raises) when the provider is not claude, no key is configured, or a cost cap is exceeded.

### `apps/thesis/services/threads.py`

**`get_or_create_review_thread(thesis)`** — uses `thesis.review_thread` FK. On first call: creates a `Thread(kind="consult", title="Post-mortem: <title>")`, saves it to `thesis.review_thread`, and returns it. Subsequent calls return the existing thread without DB writes.

### Beat task

`apps/thesis/tasks.py` — `thesis.run_due_postmortems` beat task (300s interval). Queries `PostMortem.objects.filter(status="scheduled", due_at__lte=now())` and dispatches `run_postmortem_task.delay(pm_id)` for each. Mirrors the `evaluate_triggers` pattern. `apps.thesis` added to the explicit `autodiscover_tasks([...])` list in `config/celery.py`.

## 6. Phase 3 — Decision journal

`api/journal.ts` + `useJournal` hook. `ThreadDetailPage` gains:
- "Close & journal" panel: records a `DecisionJournalEntry` (decision + note) when closing out a thread.
- "Promote to thesis" action: opens a create-thesis drawer pre-filled from the thread.
- "New thesis from this" shortcut: similar convenience action.

`JournalEntryViewSet` filters by `?thread=<id>` to keep per-thread journal lists fast.

## 7. Phase 4 — Agent presets

**`AgentPreset` model** in `apps/profiles` (not a new app) — name, `slug` (auto-slugified from name, unique), description, `objective_template` (text), `default_includes` (JSONField list), `structured` (bool), `builtin` (bool, effectively read-only — the ViewSet rejects updates to `builtin=True` rows' core fields), `active` (bool).

**Data migration** (`0005_seed_agent_presets.py`) seeds the four builtins:

| slug | name | default_includes |
|---|---|---|
| `earnings-prep` | Earnings prep | quotes, ohlc, news, chain |
| `devils-advocate` | Devil's advocate | quotes, positions, ohlc |
| `pre-trade-bias-check` | Pre-trade bias check | quotes, ohlc, breadth |
| `triage-pass` | Triage pass | quotes, positions, breadth, news |

**`AgentPresetViewSet`** at `/api/presets/` (registered on `apps/profiles/urls.py` router). Duplicate slug → 400.

**Frontend**: `api/presets.ts` + `useAgentPresets` hook. Preset dropdown in `SnapshotComposerPage` pre-fills objective and section checkboxes. Preset management in `ProfilesPage` (list + create + deactivate; builtin presets shown but not editable).

## 8. Data model summary

| Table / Change |
|---|
| `apps.thesis.Thesis` — new |
| `apps.thesis.PostMortem` — new (unique on `thesis + horizon_days`) |
| `apps.thesis.DecisionJournalEntry` — new |
| `apps.profiles.AgentPreset` — new (migrations 0004 + 0005) |
| `apps.observer.Notification.KIND_CHOICES` — `"postmortem"` added |
| `config/settings/base.py` — `THESIS_POSTMORTEM_HORIZONS = [7, 30, 90]`; `apps.thesis` in INSTALLED_APPS |
| `config/celery.py` — `apps.thesis` in autodiscover list; `run-due-postmortems` beat entry (300s) |
| `apps/market/returns.py` — new (extracted from `apps/analytics/services/leaderboard.py`) |

## 9. Key design choices

**Deterministic verdict so the loop closes without an AI key.** `objective_verdict()` reads only the thesis direction and the computed `fwd_pct` (from `OHLCBar` data already in the DB). No provider is called. A user with no Claude key still gets 7/30/90-day verdict badges on every thesis.

**Idempotent run claim guards double-billing.** The `scheduled→running` compare-and-set update is the only gate between the beat poller and the AI call. At most one concurrent caller can claim a given post-mortem row; subsequent callers are silent no-ops. This means the run-now button on `ThesisDetailPage` is safe to click multiple times.

**Journal in `apps.thesis`, not `apps.threads`.** `DecisionJournalEntry` has a FK to `Thread` but placing the model in `apps.threads` would create a threads→thesis import cycle. The FK direction (threads←journal→thesis) keeps the cycle-free.
