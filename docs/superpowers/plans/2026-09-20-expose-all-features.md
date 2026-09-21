# Expose every feature in the UI, default everything ON

Branch: `feat/expose-all-features`.

Three deliverables, in the user's words:

1. Every feature reachable from the SPA.
2. "All features should be enabled by default."
3. "I want a frontend ability to turn on and off the features" — one page, every switch.
4. Ultra-clear documentation of what can be toggled and where.

## The shape of the problem

The HTTP surface is already near-complete: of ~154 routes, every product endpoint has a
production caller. The gaps are one level down — capabilities behind a model field, an env
var, or a missing link. They cluster where a contract lives in four unsynchronised places
(model field → serializer list → hand-written TS type → rendered control) and nothing fails
when the last two are skipped.

The structural fix is a **registry with a CI drift gate**, the trick this repo already uses
for `feature_flags.py` and `scheduled_tasks.py`. Both the Features page and the toggle doc
render from it, so adding a toggle without registering it reds the build.

## "Enabled by default" means four mechanically different things

Mixing them silently no-ops. Every flip must be classified before it is written.

| Mechanism | Reaches existing rows? | Trap |
|---|---|---|
| Nullable `SystemSettings` column + Django setting default | **Yes, free** | — |
| Non-null model `BooleanField` default | New rows only | Needs `RunPython` |
| `env.bool` default | Only if the var is **absent** | Beaten by `.env.example` |
| Flag whose companion setting is empty | Never | Enabled and inert |

`runtime_config()` resolves `value if value is not None else getattr(settings, name)`, and
`apps/core/tests/test_system_settings.py::test_null_field_inherits_even_when_setting_is_truthy`
pins it. So for `SystemSettings`-backed knobs a data migration is **not needed and would be
harmful** — it replaces the NULL "inherit" sentinel with a hard value and permanently severs
the row from the setting.

## Verified findings that changed the plan

- **Extended thinking is broken on every Claude row, not merely unreachable.**
  `claude.py:71-76` sends `{"type": "enabled", "budget_tokens": N}`. That shape is removed and
  returns 400 on `claude-opus-5` (the catalog default, `catalog.py:21`), `claude-sonnet-5`,
  `claude-opus-4-8` and `claude-fable-5-1`; it is deprecated-but-working on `claude-sonnet-4-6`
  and required on `claude-haiku-4-5`. On the two rows that accept it, `types.py:24` sets
  `max_tokens = 4096` while `thinking_budget` defaults to `8000`, and the budget must be less
  than `max_tokens`. Turning the flag on therefore cannot work until the provider migrates to
  adaptive thinking (`thinking: {type: "adaptive", display: "summarized"}` +
  `output_config.effort`), keeping `budget_tokens` only for the legacy rows. `display` must be
  `"summarized"`: the new default is `"omitted"`, which streams empty `ThinkingDeltaEvent`s.
- **`AI_AUTONOMOUS_DAILY_CAP_USD` defaults to `0.0`, and `threads/tasks.py:247-249` applies the
  ceiling only `if auto_cap > 0`.** Autonomous investigation is unbounded today. A non-null
  default must land *before* `investigate` defaults on.
- **`AI_FAILOVER_ENABLED=True` is inert.** `_failover_target()` returns `None` when
  `AI_FAILOVER_PROVIDER` is `""` (the default), so the flag does nothing without an
  auto-resolver. The resolving query must `.defer("_api_key")`.
- **`.env.example:49` pins `TRADINGVIEW_TOOLS_ENABLED=false`**, and CI's compose-build job does
  `cp .env.example .env`. `env.bool`'s default only applies when the variable is absent, so
  flipping `base.py` alone reaches nothing.
- **`EventTrigger.investigate` is absent from the serializer**, not just the form — it cannot be
  set even by curl. This is an OpenAPI contract change.
- **The e2e stack runs `beat` with `MOCK_EXTERNAL=true`, and `run_structured` has no
  `MOCK_EXTERNAL` short-circuit.** Arming `ANOMALY_SWEEP_ENABLED` or `AIEVAL_SCHEDULED_ENABLED`
  would let CI spend real money on every PR if a key is present. A refusal in the billed paths
  must land before those flips.
- **`RETURNS_ADJUST_DIVIDENDS` is retroactive**, not merely expensive: it restates every
  post-mortem, Scorecard and Mirror number computed under price-return. Shipping it ON mixes two
  methodologies in one history.
- **`enable_memory` is a prompt-injection persistence channel.** Memory is one store per profile
  shared across threads; `core.prune_retention` does not touch `/data/memory/`, and there is no
  viewer or clear control. Default-on requires shipping both in the same change.

Two claims from the review were **refuted** and are not being acted on: `recomputeBook` and
`refreshRegime` are already wired (`BookPage.tsx:8`, `RegimePage.tsx:13`), and no drift gate
breaks from moving a flag into `SystemSettings` (the scheduled-work gate asserts only that a
spending task names a registered flag, and `AIEVAL_SCHEDULED_ENABLED` is already the precedent).

## Toggle inventory

72 rows. 24 global, 13 per-schedule, 9 per-profile, 5 per-provider, 5 singleton (briefing),
4 read-only env, 3 per-preset, 3 per-trigger, plus per-thesis, per-lesson, per-capture and the
always-on `vix` section. 25 of them cost real money when enabled.

Four env vars stay read-only on the page with an explicit reason, rather than silently missing:
`AI_PROVIDER_MAX_RETRIES`, `AI_PROVIDER_TIMEOUT_SECONDS`, `TRIGGER_TICK_SECONDS`,
`OBSERVER_BEAT_TIMEZONE`. `DJANGO_DEBUG` and `MOCK_EXTERNAL` are excluded entirely — a UI switch
for either is a security regression.

## Architecture

- `backend/apps/core/features.py` — frozen-dataclass registry, metadata only, **no module-level
  cross-app imports** (`apps/core/tests/test_layering.py` walks the package body). Per-object
  storage is declared as string labels and resolved with `apps.get_model()` at request time.
- `GET /api/features/` — read-only, renders the registry with live values, provenance
  (`db` / `env` / `default`) and per-object rollups. **Writes keep going to the endpoints that
  already exist** (`PATCH /api/settings/`, `PATCH /api/briefings/config/`, the ViewSets), so
  `_coerce_setting`'s guards stay the single validation path and schemathesis gains no new
  fuzzed write surface.
- `/settings/features` — renders entirely from the payload, hardcodes nothing.
- Drift gates tie registry ↔ `_SPEC` ↔ `RuntimeConfig` ↔ `FEATURE_FLAGS` ↔ model BooleanFields
  ↔ SPA routes.

## Waves

Partitioned by file tree, not by feature narrative, so no two parallel agents share a file.

- **Wave 0 — contract (serial).** `settings/base.py`, `core/{models,runtime_config,feature_flags,views}.py`,
  **one** `core/migrations/0005`, `.env.example`, `Makefile` + `e2e.yml` schemathesis exclusions,
  `api/settings.ts`, `settings/SystemSettings.tsx`. After this, no agent runs `makemigrations core`.
- **Wave 1 — backend (7 parallel, disjoint trees).** 1A pipeline (`threads/**` + `ai/**` — the
  four-way collision core), 1B profiles, 1C observer+briefing, 1D analytics+recall, 1E
  thesis+strategy, 1F backups, 1G market+snapshots+book. Then one schema regen.
- **Wave 2 — frontend (9 parallel, one surface each).** Schedules/triggers, briefing+book,
  lessons+coverage, backups/restore, scorecard+recall, profiles, threads/files/citations,
  per-object gaps, and the missing surfaces (Predictions ledger, MCP integration card,
  ProviderConfig capability controls).
- **Wave 3 — integration (serial).** `router.tsx`, nav, shortcuts, the four e2e route lists.
  `make e2e-visual-update` exactly once — all 21 baselines change from the SideNav edit alone.
- **Wave 4 — documentation (serial, sole owner of every `.md`).** `docs/toggles.md` is the
  deliverable; every earlier wave appends its CLAUDE.md delta to a scratch file and this wave
  merges.
- **Wave 5 — verification.** Full CI gate order, cost figures re-derived from one reading of
  `catalog.py`, flipped-default test audit under both orderings.

## Rulings

- **Default flips proceed as instructed**, with the safety work landing first: the autonomous
  cap becomes non-null, the tool-iteration bound lands with `enable_tools`, and the billed beat
  tasks refuse under `MOCK_EXTERNAL` before they are armed.
- **`RETURNS_ADJUST_DIVIDENDS` ships OFF** with a prominent Retroactive badge and a confirm
  dialog. It is the one flip that rewrites recorded history rather than changing future
  behaviour, so "on by default" would silently invalidate the calibration record the app exists
  to keep. Every other flip proceeds.
- **DB restore is exposed** at `POST /api/backups/<pk>/restore/`, requiring a typed confirmation
  matching the backup's filename, because the API is `AllowAny` on loopback.
- **Memory ships on with a viewer and a clear control** in the same change.
