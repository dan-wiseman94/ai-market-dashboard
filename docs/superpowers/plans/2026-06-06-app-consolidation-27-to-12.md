# App Consolidation (27 → ~12 bounded contexts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the 27 feature-tagged Django apps into ~12 bounded-context apps, break the un-contracted 5-app import cycle at the core, and add an `import-linter` **layers** contract so the spine stays acyclic by policy — without renaming a single Postgres table (zero data migration risk).

**Architecture:** "Django app = bounded context, not milestone." Each merge moves *model state* between apps with `migrations.SeparateDatabaseAndState` while pinning `Meta.db_table` to the original name, so the database is untouched. Work is ordered **lowest-risk first** (model-less apps → single-model apps → multi-model clusters). Stage 0 breaks the worst cyclic edge so the layers contract can be introduced.

**Tech Stack:** Django 5 / Postgres 17 / import-linter / drf-spectacular (schema drift gate) / pytest. All via Docker.

---

## Target structure (27 → 12)

| Keep (bounded context) | Absorbs |
|---|---|
| `core` | `backups`, `export` (infra utilities) |
| `market` | — |
| `secrets` | — |
| `ai` | `costs` (billing is one domain with `ai.cost`) |
| `snapshots` | — |
| `threads` | `files`, `warroom` (both are thread-centric: warroom spins a thread + streams over `thread.<id>`) |
| `observer` | `triggers`, `predictions` (auto-extracted from observer fires), `briefing` |
| `thesis` | `coverage`, `lessons`, `portfolio` (the house-view / learning loop around theses) |
| `analytics` | `aieval`, `dashboard` (read-only rollups; `dashboard` has no models) |
| `strategy` **(new)** | `regime` + `book` + `desk` (the M15 whole-book/regime/anomaly triad — one strategist context) |
| `recall` | — |
| `profiles` | — |

12 apps. (Net: −15 apps, −15 `AppConfig`s, −~12 `config/urls.py` includes, −~12 `TASK_PACKAGES` entries.)

### Dependency edges to fix (verified 2026-06-06)
The core is a 5-node SCC: `ai ↔ market ↔ secrets ↔ snapshots ↔ threads`, held together only by hand-written function-local imports in `ai/cost.py`, `ai/router.py`, `ai/tools/registry.py`. Worst edge: `ai/router.py:15 from apps.threads.models import Message, Thread`.

**Target layering (high → low; `|` = independent peers):**
```
dashboard(in analytics)
  └ analytics | observer | thesis | strategy
      └ threads
          └ ai | snapshots
              └ market | secrets
                  └ core
profiles, recall = leaves alongside their consumers
```

---

## The model-move recipe (table-preserving, zero-data-migration)

Used by every "absorb" below. Example: move `UserFile` from `apps.files` → `apps.threads`.

1. **Pin the table name** in the model's new home so Postgres is never touched:
```python
# backend/apps/threads/models.py  (moved verbatim from apps/files/models.py)
class UserFile(models.Model):
    # ...fields unchanged...
    class Meta:
        db_table = "files_userfile"   # keep original table; rename later (optional, cosmetic)
```
2. **Destination migration — create state only:**
```python
# backend/apps/threads/migrations/00NN_absorb_userfile.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("threads", "<prev>"), ("files", "<files_latest>")]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.CreateModel(
                name="UserFile",
                fields=[...],                 # copy the exact field tuples
                options={"db_table": "files_userfile"},
            )],
            database_operations=[],           # table already exists — touch nothing
        ),
    ]
```
3. **Source migration — delete state only:**
```python
# backend/apps/files/migrations/00NN_release_userfile.py
class Migration(migrations.Migration):
    dependencies = [("files", "<prev>"), ("threads", "00NN_absorb_userfile")]
    operations = [migrations.SeparateDatabaseAndState(
        state_operations=[migrations.DeleteModel("UserFile")],
        database_operations=[],
    )]
```
4. **Rewire code:** update every `from apps.files... import` → `from apps.threads...`; move `views.py`/`services.py`/`tasks.py`/`serializers.py` into the destination app; move the URL include in `config/urls.py`; move task modules in `config/celery.py:TASK_PACKAGES`; update `**.ApiCredential`-style patch sites in tests.
5. **Drop the empty app:** remove `"apps.files"` from `INSTALLED_APPS`; delete the now-empty package **after** its release migration is applied (keep the migration file).
6. **Verify (every move):**
   `make check-migrations` (no unexpected ops) → `make migrate` on a **fresh** DB (proves the SeparateDatabaseAndState graph is consistent) → `make migrate` on a **copy of prod** (proves no table touched) → `make test` → `make lint-imports` → `make schema` (no drift).

> **Optional cosmetic follow-up (separate PR):** once stable, `AlterModelTable("userfile", "threads_userfile")` to rename the physical table. Pure rename, reversible, no data change. Do NOT bundle with the move.

---

## Stage 0 — Break the SCC + install the layers contract

### Task 0.1: invert the `ai → threads` edge
**Files:** `backend/apps/ai/router.py:14-15`, callers in `apps/threads/*`.
- [ ] **Step 1 — characterization test:** capture current router selection for a fixed profile/override fixture (`apps/ai/tests/test_router.py` already exists — add a pin if missing).
- [ ] **Step 2 — implement:** remove `from apps.threads.models import Message, Thread` from `ai/router.py`. The router needs only the *data* it reads off those models — pass it in from the caller (`threads`) instead of importing the models. Change the router signature to accept the already-loaded thread/profile/override values; move the ORM read up into `threads.tasks._resolve_run_config`. Now `threads → ai` only; never the reverse.
- [ ] **Step 3 — run** `apps/ai apps/threads`; expected PASS, selection identical.
- [ ] **Step 4 — Commit:** `git commit -m "refactor(ai): router no longer imports threads.models (break core cycle)"`

### Task 0.2: add the layers contract
**Files:** `pyproject.toml` `[tool.importlinter]`.
- [ ] **Step 1 — add contract:**
```toml
[[tool.importlinter.contracts]]
name = "Core spine is an acyclic layering"
type = "layers"
layers = [
    "apps.threads",
    "apps.ai | apps.snapshots",
    "apps.market | apps.secrets",
    "apps.core",
]
exhaustive = false
```
- [ ] **Step 2 — run** `make lint-imports`. Expected: PASS (after Task 0.1). If it reports a remaining cycle, that edge is the next to invert (repeat 0.1's pattern) before proceeding.
- [ ] **Step 3 — Commit:** `git commit -m "ci(import-linter): contract the core spine layering"`

---

## Stage 1 — Model-less / trivial merges (lowest risk)

### Task 1.1: `dashboard` → `analytics`
`dashboard` has **no models** (verified) — pure read-rollup. No migration needed.
- [ ] Move `apps/dashboard/{views,urls,services,tests}.py` into `apps/analytics/` (namespaced, e.g. `analytics/dashboard_views.py`). Update `config/urls.py`: keep `path("api/dashboard/", include("apps.analytics.dashboard_urls"))` (URL path unchanged → no schema drift). Remove `"apps.dashboard"` from `INSTALLED_APPS`. Run `make test apps/analytics`, `make schema` (no drift). Commit.

### Task 1.2: `files` → `threads`
Apply the **model-move recipe** for `UserFile` (the worked example above). Keep `/api/files/` URL path. Commit per recipe step-group.

### Task 1.3: `costs` → `ai`
`costs` is aggregation over `AIRun`; `ai.cost` owns the math. No `costs` models (verified: 0 migs). Move `apps/costs/{services,views,urls,tests}` into `apps/ai/` (e.g. `ai/costs_views.py`). Keep `/api/costs/` include + its **ordering before generic `/api/`** (landmine). Run tests + schema. Commit.

**Stage 1 exit:** `make check` green; `/api/dashboard`, `/api/files`, `/api/costs` unchanged; 3 apps removed.

---

## Stage 2 — Single/low-model merges

### Task 2.1: new `strategy` app = `regime` + `book` + `desk`
- [ ] Scaffold `apps/strategy` (use the repo's `new-django-app` skill / `config/urls.py` ordering). Move `RegimeReading`, `BookSnapshot`, `DeskEntry` (+ their services/tasks/views) via the recipe (3 tables, `db_table` pinned to `regime_regimereading`, `book_booksnapshot`, `desk_deskentry`). Update `TASK_PACKAGES` (`regime`,`book`,`desk` → `strategy`) and `beat_schedule` task names (`regime.refresh`→`strategy.regime_refresh`, etc. — **restart worker+beat after**, landmine). Keep URL paths `/api/regime|book|desk` (mount all three under strategy.urls) to avoid schema drift, OR consolidate to `/api/strategy/...` and regenerate FE types (`pnpm gen:api`) — pick one; default: keep paths.
- [ ] Verify recipe step 6 per model. Commit per model.

### Task 2.2: `warroom` → `threads`
`WarRoomRun` (CASCADE to Thread) is thread-centric. Recipe-move `WarRoomRun` into `threads`; move `warroom/services/{personas,verdict}` into `threads/`. Keep `/api/warroom/`. Commit.

### Task 2.3: `aieval` → `analytics`
Recipe-move `EvalRun` into `analytics` (`db_table="aieval_evalrun"`). Move services + the opt-in beat task (`aieval.run_scheduled`→`analytics.aieval_run_scheduled`; restart worker+beat). Keep `/api/aieval/`. Commit.

---

## Stage 3 — Cluster merges (highest care)

### Task 3.1: `triggers` + `predictions` + `briefing` → `observer`
Largest stage. Recipe-move `EventTrigger`, `TriggerFiring`, `AIPrediction`, `BriefingConfig`, `BriefingRun` into `observer` (pin all `db_table`s). Watch the `observer.Notification.kind` enum (8 migrations already widened it) — no change needed, just keep imports. Update `TASK_PACKAGES`, `beat_schedule` task names, restart worker+beat. Keep all `/api/...` paths. Commit per model.
> Sequence-with the consolidation plan: do **after** `2026-06-06-directional-call-consolidation.md` Phase 1 so `AIPrediction` already inherits the core bases before it moves (smaller diff).

### Task 3.2: `coverage` + `lessons` + `portfolio` → `thesis`
Recipe-move `CoverageNote`, `CoverageRevision`, `Lesson`, `Position` into `thesis`. `Lesson.evidence` M2M already targets `thesis.PostMortem` (same app after move — simplifies). **Gotcha:** the `coverage/` line in `.gitignore` (the documented landmine) — ensure the moved code under `apps/thesis/` isn't caught; the `!backend/apps/coverage/` negation can be removed once `apps/coverage/` is gone. Keep `/api/coverage`, `/api/lessons`, `/api/portfolio` paths. Commit per model.

### Task 3.3: `backups` + `export` → `core`
Recipe-move `Backup`/export models into `core`; move tasks (`backups.*`,`export.*` → `core.*`); update `TASK_PACKAGES` + beat. Keep `/api/backups`, `/api/export`. Commit.

---

## Stage 4 — Tighten the contract

- [ ] Extend the layers contract to the upper tiers now that apps are merged:
```toml
layers = [
    "apps.analytics",
    "apps.observer | apps.thesis | apps.strategy",
    "apps.threads",
    "apps.ai | apps.snapshots",
    "apps.market | apps.secrets",
    "apps.core",
]
```
- [ ] `make lint-imports` green. Any violation names the remaining bad edge → invert it (Task 0.1 pattern). Commit.

**Final exit gate:** `make check` green on a fresh build; `make migrate` clean on a **prod-copy** DB (proves no table renamed/dropped); `git grep "apps.dashboard\|apps.files\|apps.costs\|apps.regime\|apps.book\|apps.desk\|apps.warroom\|apps.aieval\|apps.triggers\|apps.predictions\|apps.briefing\|apps.coverage\|apps.lessons\|apps.portfolio\|apps.backups\|apps.export"` returns only migration files + `db_table` pins; 27 → 12 apps in `INSTALLED_APPS`.

---

## Risks & mitigations
- **Migration graph consistency** is the #1 risk. Each move = a dependent pair (`SeparateDatabaseAndState`). Always test `make migrate` on a **fresh** DB AND a **prod-copy** before committing a stage; the fresh DB proves the state graph builds, the prod-copy proves no `database_operations` slipped in.
- **Beat task renames are a silent-failure landmine** (CLAUDE.md): `compose --watch` does NOT reload `worker`/`beat`. After any `TASK_PACKAGES`/`beat_schedule` change, `docker compose restart worker beat` or the task won't register/fire. Add this to every stage's checklist.
- **URL-include ordering landmine:** specific prefixes (`/api/costs/`) must stay registered before the generic `/api/` includes. Re-verify `config/urls.py` after each move.
- **Schema drift gate:** keeping URL paths unchanged means `make schema` shows no drift; if you consolidate paths instead, regenerate `backend/schema.yml` + `pnpm gen:api` in the same commit.
- **Reversibility:** every migration is `SeparateDatabaseAndState` with empty `database_operations`, so each move is reversible by reversing the state ops — no data is ever at risk. The cosmetic `AlterModelTable` renames (deferred) are the only DB-touching ops and are trivially reversible.
- **Do this AFTER the consolidation plan's Phase 1**, so `AIPrediction`/`PostMortem` already share the core bases and move as smaller diffs.

## Self-review checklist
- [ ] All 15 absorbed apps have a destination + recipe task (dashboard, files, costs, regime, book, desk, warroom, aieval, triggers, predictions, briefing, coverage, lessons, portfolio, backups, export = 16 listed; `portfolio` optional-fold noted).
- [ ] Layers contract added only AFTER the cycle-breaking task; tightened in Stage 4.
- [ ] Every stage lists: tests + check-migrations + lint-imports + schema + worker/beat restart.
- [ ] No physical table rename in the move itself (db_table pinned); renames deferred to optional cosmetic PRs.
