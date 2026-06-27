# Test-Suite Hardening & Coverage — Design

**Date:** 2026-06-27
**Status:** Approved (design); plan + implementation to follow
**Scope:** Milestone — phased across both the e2e (Playwright/Python) and Storybook suites.
**Related:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` (original e2e design), `docs/superpowers/specs/2026-04-18-frontend-test-coverage-design.md`.

## 1. Motivation

Both suites are *broad but uneven*. A read-only audit (4 parallel readers over Storybook,
the e2e ui/visual/a11y lanes, the ws/api/perf/CI wiring, and a frontend inventory
cross-reference) found that the biggest risk is **false confidence**: tests that read green
but assert nothing, lanes that are installed but never run, and baselines so brittle they get
masked into uselessness. Closing real coverage gaps matters too, but only *after* the
foundation is trustworthy.

### Audit findings (condensed)

**Storybook** (13 stories / 76 components / 0 of 64 pages)
- 63 components have no story, including the repo's mandated primitives (`ErrorBoundary`,
  `Toasts`) and the highest-value interactive/data components (`RuleBuilder`/`LeafRow`/
  `FiringsTable`, `CommandPalette`, `OptionChainTable`, `ToolCallTrace`, `settings/*`, and the
  data-fetching `dashboard/`·`analytics/`·`costs/` tiles).
- MSW is wired globally (`preview.tsx`) but used by only 2 stories (`PositionsTable`,
  `WatchlistTable`); every self-fetching component renders empty in the browser lane.
- a11y runs as `a11y: { test: "todo" }` — violations are surfaced but **never fail** the CI
  storybook job. Several play functions are shallow or absent (`StopButton`, `ThemeToggle`).
- `@chromatic-com/storybook` + `chromatic` are installed but **completely inert** — no token,
  no CI job, no script. There is **no visual-regression gate anywhere** (the Playwright visual
  lane is also not in CI). The browser lane only ever renders the **dark** theme
  (`initialGlobals.theme = "dark"`).

**E2E** (6 lanes, 20 ui files, 25 page objects)
- ~17 routes have **zero** ui/visual/a11y coverage — almost the entire M15 "strategy" surface
  (`warroom`, `warroom/:id`, `desk`, `regime`, `coverage/:ticker`) plus `book`, `scorecard`,
  `mirror`, `recall`, `portfolio`, `themes`, `market-data`, `snapshots` (list), `settings/system`,
  `settings/connections`, `theses/new`, `errors`.
- **Overpromising tests**: `test_create_simple_trigger_and_fire_now` only checks Save is
  disabled; schedule-run, caps-edit, snapshot-capture flows assert mere *visibility*. The POM
  methods to actually drive them (`SnapshotPage.capture`, `TriggerEditorPage.fill_simple/save`,
  `SchedulesPage.create/run_now`, `CostsPage.set_caps`, the entire `SchwabOAuthPage`) **exist
  but are never called.**
- **Flakiness**: pervasive `networkidle` (`base.py`, `visual.py:50`, a11y); a literal
  `"Mocked response"` text-wait (`thread_detail.py:49`); a `g`-shortcut loop that swallows
  failures (`except Exception: continue`, `test_keyboard_and_palette.py:37`); keyboard a11y
  guarded by `pytest.skip` on failure (`test_keyboard_only.py:30,36` — regressions *skip*
  instead of fail); weak selectors (`ul.first`, `body:has-text('$')`); a `console_guard`
  allow-list broad enough to mask broken-route errors (`"Error handled by React Router default
  ErrorBoundary"`, blanket `404`/`ERR_FAILED`).
- The **ws lane is excluded from CI entirely** and misses the stop/cancel frame, error frames,
  `capability_warning`, snapshot `failed`/`section_failed`, and war-room streaming.
- The **perf lane is effectively dead** — silent `pytest.skip` on a docker-exec/URL/overlay
  mismatch, never run in CI.
- The **visual differ is byte-exact** (`visual.py:94`) — any 1-byte change fails, forcing broad
  masks (`/costs` is excluded entirely); light-theme-only, single 1280×800 viewport.
- CI (`e2e.yml`) runs only api+ui+schemathesis+render-chart, serially in one 35-min job.

## 2. Goals / Non-goals

**Goals**
1. Eliminate false-confidence constructs (swallowed failures, skip-on-failure, visibility-only
   tests named like flows, inert tooling).
2. De-flake the existing lanes (deterministic waits, stable selectors, pixel-tolerant visual diff).
3. Close the highest-value coverage gaps: the ~17 dark routes, the unexercised write-flows, and
   the mandated/high-value Storybook components with MSW-backed states and real play tests.
4. Make a11y actually gate (Storybook `todo → error`; broaden axe routes; real keyboard journeys).
5. Wire the hardened lanes into CI as a per-lane matrix with appropriate gating.

**Non-goals**
- No Chromatic cloud adoption (decided: harden the local Playwright lane instead).
- No new product features or UI redesign. We add `data-testid` anchors and may add small
  test affordances, but we do not change user-facing behavior.
- No change to the network-isolation security posture (no auth added; bindings stay 127.0.0.1).
- Not chasing 100% story/route coverage — we target the high-value set and add a *guard* so new
  gaps are caught going forward.

## 3. Decisions

- **Visual regression:** Harden the local Playwright lane (pixel-tolerance diff + more
  baselines). No Chromatic.
- **Perf lane:** Fix it (correct the docker-exec/URL/overlay mismatch + add throttling) and wire
  it as an **advisory artifact** (not a hard gate). Keep it alive rather than delete it.
- **WS lane in CI:** Include behind `continue-on-error` with a tracking note, rather than leave
  it entirely off — surfaces regressions without blocking PRs on the known Channels-delivery flake.
- **Chromatic dependency:** Remove `@chromatic-com/storybook` + `chromatic` (chosen path is the
  Playwright lane) to cut audit/supply-chain surface. The `addon-a11y` and `addon-vitest`
  addons stay.

## 4. Phased design

Ordering is **harden → expand → gate** (see §6 for dependency rationale).

### Phase 0 — Kill false confidence (correctness; no new coverage)
Lowest-risk, highest-value. Make every assertion mean something.
- `test_keyboard_and_palette.py`: replace the `except Exception: continue` loop with an explicit
  per-shortcut assertion that navigation actually occurred; cover all 13 shortcuts in
  `useKeyboardShortcuts.ts` (current map covers 7). Refresh the stale docstring.
- `a11y/test_keyboard_only.py`: replace both `pytest.skip(...)` escape hatches with hard
  failures (reaching the Snapshot link via Tab and activating it are *requirements*, not
  optional). Strengthen the focus-ring check beyond UA-default `outline`.
- Rename overpromising tests so the name matches what they assert today (the real flow upgrades
  land in Phase 2): e.g. `test_create_simple_trigger_and_fire_now` →
  `test_trigger_editor_disables_save_until_named`.
- `console_guard.py`: scope the React-Router-ErrorBoundary and blanket `404`/`ERR_FAILED`
  patterns to specific benign URLs so broken-route/failed-resource regressions surface again.
- Doc drift: seed-ladder docstring "7 rungs" → 8 (`thesis` is a side-branch off `threads`);
  storySort `order` taxonomy in `preview.tsx` (add `Layout`).

### Phase 1 — De-flake + visual differ
- Replace `networkidle` readiness with explicit role/element waits. Introduce a
  `wait_ready`/`wait_for_app_ready` helper keyed on a stable app-shell signal (e.g. the rendered
  `<main>`/nav landmark + skeleton-detached) and migrate `base.py`, `visual.py:wait_for_stable`,
  and the a11y/observer/snapshots call sites off `networkidle`.
- Replace the literal `"Mocked response"` wait (`thread_detail.py`) and weak selectors with
  `data-testid`-anchored locators. Add stable testids to components where missing (test-only
  anchors, no behavior change).
- **Visual differ:** swap byte-exact compare in `helpers/visual.py:capture_or_compare` for a
  pixel-tolerance diff (Pillow + a small per-pixel/percentage-of-pixels threshold; pure-Python,
  already have Pillow transitively or add it to the e2e deps). Keep the `.actual.png` +
  `make e2e-visual-update` workflow. Tolerance lets `/costs` back in and stops sub-pixel/AA churn.
- Add a dark-theme capture path and a second viewport hook to `visual/conftest.py` so Phase 3
  can add dark + responsive baselines without re-plumbing.

### Phase 2 — Drive the real write-flows (ui-lane depth)
Wire the already-built, unused POM methods into real assertions:
- **Snapshot capture** end-to-end: select profile + objective → Capture → section progress →
  Send-to-AI (`SnapshotPage.capture/wait_for_complete/send_to_ai`).
- **Trigger create + fire-now** (`TriggerEditorPage.fill_simple/fill_dsl/save/backtest` + fire).
- **Schedule create + run-now** (`SchedulesPage.create/run_now`).
- **Cost caps edit** (`CostsPage.caps_editor/set_caps`) + assert persistence.
- **Thesis create** on `/theses/new` (pre-trade discipline: rejects empty rationale / missing
  invalidation; accepts a valid thesis).
- **Command-palette execution** (run a command, not just open), **notification drawer**,
  **file attach** (`FileAttachPanel` in `ThreadDetailPage`).
- **Schwab `/settings/connections`** browser pass (status pill, Connect/Reconnect) — revives the
  dead `SchwabOAuthPage` POM.
- Keyboard journeys through the command palette, Compare dialog, and close-thesis modal
  (open / Esc-to-close / focus-trap).

### Phase 3 — Close the route gaps (+ seed rungs)
- New seed rungs so the dark routes render with real data:
  - `strategy` rung: `CoverageNote`+`CoverageRevision` (for `/coverage/:ticker`), a war-room
    debate + messages (`/warroom`, `/warroom/:id`), a desk anomaly sweep (`/desk`), `RegimeReading`
    (`/regime`).
  - `recall` rung: searchable embedded items (`/recall`).
  - `book` rung: `BookSnapshot` (`/book`, the `PositionsBookTile`).
  - `predictions` rung: `AIPrediction` ledger rows (feeds `/scorecard`, `/mirror` context).
  - `market-events` already seeded by `market`; extend if `/events` needs populated calendars.
  Respect the advisory-lock + idempotency conventions; wire each rung into the ladder in
  `conftest.py` with the correct dependency edges (and a meta-test asserting the chain — Phase 5).
- For each of the ~17 uncovered routes: a minimal **ui smoke** (renders, no ErrorBoundary, key
  landmark visible), an **axe** scan (add to `a11y/test_axe_per_route.py`), and a **visual
  baseline** (light + dark). Add the POMs needed.
- Broaden the axe route list (~20 routes) and resolve dynamic ids deterministically
  (`order_by` instead of bare `.first()`).

### Phase 4 — Storybook coverage + MSW + a11y gate
- Stories for the mandated primitives (`ErrorBoundary`, `Toasts`) and the high-value set
  (`RuleBuilder`/`LeafRow`/`FiringsTable`, `CommandPalette`, `OptionChainTable`, `ToolCallTrace`,
  `QuoteCell`, `MarketStatusBadge`, `NotificationBell`, `ui/Toggle`, `settings/*`,
  `thesis/ThesisBadges`, and the data-fetching `dashboard/`·`analytics/`·`costs/` tiles).
- A **shared MSW handler module** (`src/__tests__/msw/handlers.ts` or `.storybook/msw/`) reused
  across data stories — model loading/error/empty/populated states the way `PositionsTable`
  already does. Bring `WatchlistTable` up to that pattern (add loading/error/empty).
- Real **play** functions for new stories and the thin existing ones (`StopButton` click,
  `ThemeToggle` cycle).
- **a11y gate:** promote `a11y.test` from `"todo"` → `"error"` (start with primitives/layout,
  then widen). Where a violation is a known false positive, suppress per-story with a documented
  reason, never globally.
- **Light theme:** add a light-theme assertion path so the browser lane exercises both canvases
  (parametrize theme-sensitive stories or add a `Light` variant).
- **Story guard:** a check (lint rule or meta-test) that flags story-less components in
  high-value dirs so new components can't silently ship without a story.
- Remove `@chromatic-com/storybook` from `main.ts` addons and drop both Chromatic deps.

### Phase 5 — CI wiring + harness hardening
- Fan `e2e.yml` into a per-lane **matrix** (api / ui / ws / visual / a11y) — isolates failures,
  adds parallelism, gives per-lane signal. `ws` runs with `continue-on-error: true` (+ a tracking
  note); `visual` + `a11y` become gates now that they're hardened and have committed baselines.
- **Perf:** fix `lighthouse_runner` (run lighthouse against the actually-served URL for the
  overlay; don't `docker exec` from inside the container; add network throttling) and publish
  `median.json`/`.html` as an **advisory** artifact (not a gate).
- **Meta-tests:** `test_gha_workflow.py` asserts *every* lane step exists (api, schemathesis,
  render-chart, ui, matrix lanes, teardown). New meta-test: every scenario in the registry maps
  to a **distinct** provider/service handler (catch `handler_for` silent fallback). New
  meta-test: the conftest seed-fixture dependency chain matches the documented ladder (incl.
  `thesis` as a side-branch).
- Storybook job (`check.yml`) gains the a11y gate via the `error` setting (no new job needed).

## 5. Components & interfaces (what changes, where)

| Area | Files (representative) | Change |
|---|---|---|
| Swallowed failures | `e2e/ui/test_keyboard_and_palette.py`, `e2e/a11y/test_keyboard_only.py` | Assert instead of skip/continue |
| Console guard | `e2e/helpers/console_guard.py` | Scope benign patterns to URLs |
| Readiness | `e2e/pages/base.py`, `e2e/helpers/visual.py`, a11y/observer/snapshots tests | `networkidle` → element/role waits |
| Visual differ | `e2e/helpers/visual.py`, `e2e/visual/conftest.py`, `e2e/tests/test_visual_helpers.py` | Pixel tolerance; dark + viewport hooks |
| Write-flows | `e2e/ui/test_*.py` + existing POMs (`snapshot.py`, `trigger_editor.py`, `schedules.py`, `costs.py`, `schwab_oauth.py`) | Drive the named flows |
| Seed rungs | `e2e/fixtures/seed_strategy.py` (+ recall/book/predictions), `e2e/conftest.py` | New rungs + ladder edges |
| Route coverage | `e2e/ui/test_<route>.py`, `e2e/pages/<route>.py`, `e2e/a11y/test_axe_per_route.py`, `e2e/visual/test_route_snapshots.py` | Smoke + axe + baseline per route |
| Stories | `frontend/src/components/**/*.stories.tsx`, `frontend/src/__tests__/msw/handlers.ts` | New stories + shared MSW |
| a11y gate | `frontend/.storybook/preview.tsx` | `todo → error` |
| Story guard | `frontend/` lint or `e2e/tests/`/`frontend` meta-test | Flag story-less components |
| Chromatic removal | `frontend/.storybook/main.ts`, `frontend/package.json` | Drop addon + deps |
| CI | `.github/workflows/e2e.yml`, `e2e/tests/test_gha_workflow.py`, `test_makefile.py`, new meta-tests | Matrix + gates + harness assertions |
| Perf | `e2e/helpers/lighthouse_runner.py`, `e2e/perf/*` | Fix runner; advisory artifact |

## 6. Sequencing & dependencies

```
Phase 0 (false confidence)         ── independent, ship first
Phase 1 (de-flake + pixel diff)    ── visual differ is a prerequisite for new baselines
Phase 3 seed rungs                 ── prerequisite for populated baselines + route tests
        │
        ▼
Phase 2 (flows) ── Phase 3 (routes) ── Phase 4 (stories)   ── parallelizable on the foundation
        │
        ▼
Phase 5 (CI gating)                ── last; only gate lanes once green + deterministic
```

Rationale: adding 17 routes of baselines on a 1-byte-fragile differ, or wiring flaky/empty lanes
into CI, manufactures churn. Build the reliable foundation, expand on it, gate at the end.

## 7. Testing approach (how we verify this work)

- **Helpers/meta-tests** (visual differ, console_guard, scenario→handler map, ladder chain) are
  unit-level and run in the `backend`/`web` container without the full stack — fast TDD loop.
- **New ui/a11y/visual tests** run via `make e2e-one t=<lane>/<file>.py` against the e2e overlay
  (`make e2e-up`), `HEADED=1` to debug. Visual baselines are generated with
  `make e2e-visual-update`, inspected, then committed.
- **Storybook** stories run via `pnpm exec vitest --project storybook run` (browser lane) — the
  same command CI uses.
- Each phase ends green on its targeted commands before commit; Phase 5 confirms the full
  `make e2e` + the storybook job locally.

## 8. Risks & mitigations

- **Shared non-rolled-back live DB** → new seed rungs must be idempotent under the advisory lock;
  new tests must not assume an empty DB (use page-1-tolerant assertions or create-then-find).
- **WS-in-CI flake** → gated `continue-on-error`, not a hard gate; a follow-up can attempt the
  Channels-delivery fix.
- **Pixel tolerance too loose** → start tight (small percentage-of-pixels threshold), tune per
  baseline; keep `baseline-size-guard` so masks don't silently swallow regions.
- **a11y `error` floods red** → roll out per-story/per-route, suppress documented false positives
  individually, never globally re-disable.
- **Scope creep** → the *guard* (story-less + axe-route + meta-tests) is the durable backstop;
  we target the high-value set, not exhaustive coverage, this milestone.

## 9. Out of scope / follow-ups

- Channels-delivery fix to make the ws lane a hard CI gate.
- Stateful/`coverage`-phase schemathesis fuzzing (tooling generator bug currently blocks it).
- Responsive/mobile visual baselines beyond the one added viewport hook.
- Story coverage for the long tail of low-value primitives.
