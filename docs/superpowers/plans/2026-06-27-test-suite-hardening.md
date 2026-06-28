# Test-Suite Hardening & Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the e2e (Playwright/Python) and Storybook suites trustworthy and well-covered — kill false-confidence constructs, de-flake, add a pixel-tolerant visual differ, drive the unexercised write-flows, close ~17 dark routes, add high-value stories with MSW + a real a11y gate, and wire the hardened lanes into CI.

**Architecture:** Harden → expand → gate. Phase 0 (correctness) and Phase 1 (de-flake + pixel diff) build a reliable foundation; Phases 2–4 expand coverage on it (flows, routes, stories) in parallel; Phase 5 wires CI gates last.

**Tech Stack:** pytest + Playwright (Python sync API), Docker Compose e2e overlay (`MOCK_EXTERNAL=true`), Storybook 10 + `@storybook/addon-vitest` browser lane (`@vitest/browser-playwright` chromium), `msw-storybook-addon`, Pillow (new, for pixel diff), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-06-27-test-suite-hardening-design.md`

## Global Constraints

- **Everything runs in Docker.** e2e lanes exec in containers: `api`/`ws` in `web`, `ui`/`visual`/`a11y` in `worker` (carries chromium). Use `make e2e-up` then `make e2e-one t=<lane>/<file>.py`; `HEADED=1` to debug. One backend/meta test: `docker compose exec web pytest e2e/tests/test_x.py -v` (container WORKDIR `/app/backend`; pass `--workdir /app` for e2e paths). Storybook: `docker compose exec frontend pnpm exec vitest --project storybook run`.
- **Never set `MOCK_EXTERNAL` on the dev stack.** The e2e overlay (`compose.e2e.yaml`) sets it; the dev stack must not.
- **e2e seeds write to the LIVE Postgres** the `web` container reads (the pytest-django blocker is bypassed in `e2e/conftest.py:91`). All new seeds must be idempotent and wrapped in `_seed_lock()` (pg advisory lock key `730426`).
- **Section terminal state is `"done"`; only the parent `Snapshot` is `"ready"`.** Snapshot images via `image_store.read_image_bytes`, never `bytes(img.data)`.
- **DRF exposes FK ids as `*_id`** — POMs/contract assertions must use `thread_id` etc.
- **Pre-commit hook caveat:** staging `e2e/*.py` trips the web-container ruff hook (E902 — web only mounts `backend/`). Commit with `LEFTHOOK=0 git commit ...` (or `--no-verify`) when e2e Python is staged, then `make lint` separately.
- **`gen:api` in the frontend container** can't resolve `../backend/schema.yml`; don't regenerate FE types from there.
- **CI per-commit gate runs `-p no:randomly`** (definition order). Keep `backend/conftest.py` autouse fixtures intact.
- Conventional commits (`test(e2e):`, `fix(e2e):`, `feat(frontend):`, `chore:`, `ci:`). Frequent, bite-sized.

---

## Phase 0 — Kill false confidence

No new coverage; make existing assertions mean something. Independently shippable.

### Task 0.1: Console guard — stop masking broken-route errors

**Files:**
- Modify: `e2e/helpers/console_guard.py`
- Test: `e2e/tests/test_console_guard.py`

**Interfaces:**
- Produces: `console_guard.attach(page) -> list[str]` (unchanged signature); `ALLOWED_CONSOLE_PATTERNS` no longer matches the React-Router default-ErrorBoundary message or a blanket `404`/`ERR_FAILED`.

- [ ] **Step 1: Write the failing test.** Add to `e2e/tests/test_console_guard.py`:

```python
import re
from e2e.helpers import console_guard


class _Msg:
    def __init__(self, type_: str, text: str) -> None:
        self.type = type_
        self.text = text


class _FakePage:
    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}

    def on(self, event: str, cb: object) -> None:
        self._handlers[event] = cb

    def emit_console(self, text: str) -> None:
        self._handlers["console"](_Msg("error", text))


def test_react_router_errorboundary_is_not_masked():
    page = _FakePage()
    errors = console_guard.attach(page)
    page.emit_console("Error handled by React Router default ErrorBoundary: Error: 404")
    assert errors, "router ErrorBoundary console error must surface (broken-route regression)"


def test_genuine_404_still_surfaces():
    page = _FakePage()
    errors = console_guard.attach(page)
    page.emit_console("Failed to load resource: the server responded with a status of 404 (Not Found) /api/widgets/")
    assert errors, "an unexpected 404 must surface; only known-benign URLs are allowed"


def test_known_benign_files_404_is_allowed():
    page = _FakePage()
    errors = console_guard.attach(page)
    page.emit_console("Failed to load resource: 404 (Not Found) /api/files/")
    assert not errors, "the documented benign /api/files/ 404 stays allow-listed"
```

- [ ] **Step 2: Run to verify failure.** `docker compose exec --workdir /app web uv run pytest e2e/tests/test_console_guard.py -v` → FAIL (router/404 currently masked).

- [ ] **Step 3: Implement.** In `console_guard.py`, remove the bare `re.compile(r"\b404\b.*Not Found")`, the `re.compile(r"Error handled by React Router default ErrorBoundary")`, and the blanket `re.compile(r"Failed to load resource: net::ERR_FAILED")`. Replace the 404 entry with URL-scoped benign patterns only:

```python
    # Same-origin proxy 404s that the UI handles via EmptyState — scope to the
    # specific endpoints known to 404 before data exists, so an UNEXPECTED 404
    # (e.g. a broken route fetching a missing endpoint) still fails the test.
    re.compile(r"404 \(Not Found\).*/api/files/"),
    re.compile(r"404 \(Not Found\).*/api/(recall|predictions)/"),
```

Leave the websocket/font/`ERR_CONNECTION_REFUSED` allowances. Do NOT keep the router-ErrorBoundary allowance — broken-route navigation must fail.

- [ ] **Step 4: Run to verify pass.** Same command → PASS (3 new tests + existing).

- [ ] **Step 5: Commit.** `LEFTHOOK=0 git commit -am "fix(e2e): scope console-guard 404 allowance so broken routes fail"`

### Task 0.2: g-shortcut test — assert navigation instead of swallowing

**Files:**
- Modify: `e2e/ui/test_keyboard_and_palette.py`
- Reference: `frontend/src/hooks/useKeyboardShortcuts.ts` (the real shortcut map — read it to get all 13)

**Interfaces:**
- Consumes: `DashboardPage`. Produces: a parametrized test that fails if any shortcut doesn't navigate.

- [ ] **Step 1.** Read `frontend/src/hooks/useKeyboardShortcuts.ts` and build the complete `SHORTCUTS` map (all `g <x>` pairs — the audit says 13 exist; the current test has 7).
- [ ] **Step 2: Rewrite the test** to assert each navigation and `@pytest.mark.parametrize` per shortcut so one broken shortcut fails precisely:

```python
@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.parametrize("keys,expected", list(SHORTCUTS.items()))
def test_g_shortcut_navigates(page, frontend_base_url, minimal, keys, expected) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    page.keyboard.press("Escape")
    for key in keys.split():
        page.keyboard.press(key)
    page.wait_for_url(lambda u, e=expected: u.rstrip("/").endswith(e.rstrip("/")) or e in u, timeout=4_000)
```

No `try/except`. The `wait_for_url` raising IS the assertion.

- [ ] **Step 3: Run** (needs overlay): `make e2e-up && make e2e-one t=ui/test_keyboard_and_palette.py` → all shortcut params PASS. If a shortcut genuinely isn't wired, that's a real finding — note it, don't swallow it.
- [ ] **Step 4: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): assert every g-shortcut navigates (was swallowing failures)"`

### Task 0.3: Keyboard-only a11y — fail instead of skip

**Files:** Modify `e2e/a11y/test_keyboard_only.py`

- [ ] **Step 1: Rewrite** so the two `pytest.skip(...)` calls become `pytest.fail(...)` (reaching + activating the Snapshot link are requirements). Strengthen the focus-ring check to reject the UA default (require a non-default `outline-width`/color or a `box-shadow` ring), and assert it on the focused link *before* Enter, not just after. Keep the Tab-budget at 25 but `pytest.fail` if not found.
- [ ] **Step 2: Run** `make e2e-one t=a11y/test_keyboard_only.py` (overlay up) → PASS. If it fails, that's a real keyboard-nav/focus-ring gap — fix the app affordance or record it as a follow-up bug, don't re-add the skip.
- [ ] **Step 3: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): keyboard-only a11y journey fails (not skips) on regression"`

### Task 0.4: Rename overpromising tests to match current assertions

**Files:** Modify `e2e/ui/test_triggers.py`, `e2e/ui/test_observer.py`, `e2e/ui/test_snapshots.py` (and any other test whose name claims a flow it doesn't drive — audit list in spec §1).

- [ ] **Step 1.** Rename (function + any references) so the name describes the assertion, e.g.:
  - `test_create_simple_trigger_and_fire_now` → `test_trigger_editor_disables_save_until_named`
  - `test_trigger_backtest_runs_against_ohlc` → `test_trigger_backtest_tab_renders`
  - `test_create_schedule_and_run_now` → `test_schedule_row_and_run_now_button_visible`
  - observer diff/structured render-only tests → `..._renders` names.
  (The real flow-driving versions are added in Phase 2 — these renames prevent a green name from implying a flow is covered when it isn't.)
- [ ] **Step 2: Run** the affected files (overlay up) → PASS (rename only, no logic change).
- [ ] **Step 3: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): rename visibility-only tests so names match assertions"`

### Task 0.5: Doc-drift fixes

**Files:** Modify `e2e/conftest.py` (docstring line ~141), `frontend/.storybook/preview.tsx` (storySort `order`).

- [ ] **Step 1.** `conftest.py`: change "7 rungs" → "8 rungs (thesis is a side-branch off threads)" and reflect the actual chain in the comment.
- [ ] **Step 2.** `preview.tsx`: add `"Layout"` to the storySort `order` array so `Layout/*` titles aren't dumped in the `*` bucket.
- [ ] **Step 3: Commit.** `LEFTHOOK=0 git commit -am "docs(e2e): fix seed-ladder rung count and storybook storySort taxonomy"`

---

## Phase 1 — De-flake + pixel-tolerant visual differ

### Task 1.1: Pixel-tolerant visual diff (replace byte-exact)

**Files:**
- Modify: `e2e/helpers/visual.py`
- Test: `e2e/tests/test_visual_helpers.py`
- Modify (deps): add `pillow` to the e2e/test dependency group in `pyproject.toml` if not present (`numpy` optional — pure-Pillow is fine).

**Interfaces:**
- Produces: `capture_or_compare(page, name, *, mask=None, max_diff_ratio: float = 0.001) -> None` — compares decoded pixels; raises `AssertionError` only when the fraction of differing pixels (beyond a small per-channel threshold) exceeds `max_diff_ratio`. Still writes `<name>.actual.png` on failure; still creates baseline on first run.

- [ ] **Step 1: Write failing tests** in `test_visual_helpers.py`: a helper `_png(color, size=(8,8))` builds PNG bytes via Pillow; assert (a) identical images pass, (b) a single-pixel change within `max_diff_ratio` passes, (c) a large block change fails and writes `.actual.png`. Drive `capture_or_compare` with a fake `page` whose `.screenshot(...)` returns the bytes.
- [ ] **Step 2: Run** `docker compose exec --workdir /app web uv run pytest e2e/tests/test_visual_helpers.py -v` → FAIL (byte-exact differ rejects the 1-pixel case / no `max_diff_ratio`).
- [ ] **Step 3: Implement** the Pillow-based diff: decode baseline + actual to `RGB`, resize-guard (fail fast on dimension mismatch with a clear message), count pixels whose max per-channel delta exceeds a small constant (e.g. 16), compute ratio over total, compare to `max_diff_ratio`. Keep masks (Playwright still paints mask boxes before screenshot).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.** `LEFTHOOK=0 git commit -am "feat(e2e): pixel-tolerant visual diff (replaces byte-exact compare)"`

### Task 1.2: Deterministic readiness — retire networkidle

**Files:**
- Modify: `e2e/pages/base.py` (`wait_ready`), `e2e/helpers/visual.py` (`wait_for_stable`), call sites in `e2e/ui/test_observer.py`, `e2e/ui/test_snapshots.py`, `e2e/ui/test_files_and_citations.py`, `e2e/a11y/test_axe_per_route.py`, `e2e/a11y/test_keyboard_only.py`.

**Interfaces:**
- Produces: `BasePage.wait_ready()` waits on the app-shell landmark (e.g. `page.get_by_role("main")` visible) + skeleton-detached, NOT `networkidle`. Add `wait_for_app_ready(page)` in `e2e/helpers/` if a shared free function is cleaner for non-POM call sites.

- [ ] **Step 1.** Implement the element/role-based wait (read `AppLayout.tsx` to confirm a stable landmark — `<main>` / nav role / a `data-testid="app-shell"`). Add the testid to `AppLayout.tsx` if no stable landmark exists (test-only anchor).
- [ ] **Step 2.** Replace each `page.wait_for_load_state("networkidle")` with the new wait. Grep to confirm none remain in the lanes: `rg "networkidle" e2e/`.
- [ ] **Step 3: Run** the touched files (overlay up) → PASS, and confirm the visual lane still matches baselines (`make e2e-one t=visual/test_route_snapshots.py`).
- [ ] **Step 4: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): replace networkidle with deterministic app-shell waits"`

### Task 1.3: Stable locators — kill literal-text/weak waits

**Files:** Modify `e2e/pages/thread_detail.py` (`wait_for_done`), `e2e/ui/test_costs.py`, `e2e/ui/test_observer.py`, and any component needing a `data-testid` anchor (`frontend/src/...`).

- [ ] **Step 1.** `thread_detail.py:wait_for_done`: stop keying on literal `"Mocked response"`; wait on the assistant message reaching a `done` state via a stable anchor — add `data-testid="message-status-done"` (or reuse an existing role) to the message component in `frontend/src/pages/thread-detail/` and wait on that.
- [ ] **Step 2.** Replace `page.locator("ul").first`, `body:has-text('$')`, `text=Today` with testid-anchored locators (add `data-testid` where missing).
- [ ] **Step 3: Run** the affected ui files + the ws lane smoke (`make e2e-one t=ui/test_threads.py`) → PASS.
- [ ] **Step 4: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): anchor thread/cost waits on data-testid (not literal text)"`

### Task 1.4: Visual conftest — dark + viewport hooks

**Files:** Modify `e2e/visual/conftest.py`, `e2e/visual/test_route_snapshots.py`.

- [ ] **Step 1.** Add a `color_scheme`/`theme` parameter hook and a second viewport constant so Phase 3 can request dark + a narrow viewport per route without re-plumbing. Default stays light/1280×800 so existing baselines are unaffected. Verify existing baselines still pass.
- [ ] **Step 2: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): visual conftest gains dark-theme + viewport hooks"`

---

## Phase 2 — Drive the real write-flows (ui-lane depth)

Each task wires an existing-but-unused POM into a real flow assertion. Pattern per task: read the page + POM, write the flow test using the POM methods, run via `make e2e-one`, commit. All `@pytest.mark.integration @pytest.mark.ui`.

> **Execution note:** Tasks 2.1–2.8 are independent and fan out to parallel subagents. Each MUST run its lane file green (overlay up) before committing.

- [ ] **Task 2.1 — Snapshot capture end-to-end.** `e2e/ui/test_snapshots.py` + `e2e/pages/snapshot.py`. Drive `SnapshotPage.capture(profile, objective, includes)` → `wait_for_complete()` (assert per-section progress reaches terminal `done`; remember section state is `"done"` not `"ready"`) → `send_to_ai()` → assert a thread/assistant turn appears. Use the `default` scenario (deterministic mock capture).
- [ ] **Task 2.2 — Trigger create + fire-now.** `e2e/ui/test_triggers.py` + `e2e/pages/trigger_editor.py`. `fill_simple(...)` (name + a price/pct leaf) → `save()` → assert row in list → fire-now → assert a firing row / notification. Add a separate DSL variant via `fill_dsl(...)`.
- [ ] **Task 2.3 — Schedule create + run-now.** `e2e/ui/test_observer.py` + `e2e/pages/schedules.py`. `create(interval, mode)` → assert row → `run_now()` → assert observer timeline gains an entry. Mind the `set_enabled` race (read `is_checked()` AFTER the refetch settles — use a wait, not a point-in-time read).
- [ ] **Task 2.4 — Cost caps edit.** `e2e/ui/test_costs.py` + `e2e/pages/costs.py`. `set_caps(daily, monthly)` → reload → assert persisted values via the editor + (optionally) `GET /api/settings/` shape.
- [ ] **Task 2.5 — Thesis create (pre-trade discipline).** New `e2e/ui/test_thesis_create.py` + extend `e2e/pages/theses.py`. On `/theses/new`: assert Save rejected with empty rationale AND with no invalidation; assert a thesis with rationale + invalidation_price persists (remember: validation is create-only).
- [ ] **Task 2.6 — Command-palette execution + file attach.** `e2e/ui/test_keyboard_and_palette.py` (execution) + `e2e/ui/test_files_and_citations.py` (attach). Run a palette command and assert the resulting navigation/action; attach a file via `FileAttachPanel` and assert it appears (use the `files-upload-fail` scenario for the error path too).
- [ ] **Task 2.7 — Schwab connections page (browser).** New `e2e/ui/test_connections.py` using the dead `SchwabOAuthPage` POM. Under `schwab-oauth-ok` scenario, load `/settings/connections`, assert the status pill + Connect/Reconnect affordance. This revives the POM (otherwise dead code).
- [ ] **Task 2.8 — Keyboard journeys for overlays.** Extend `e2e/a11y/test_keyboard_only.py` (or new file): command palette (open via Cmd/Ctrl-K, Esc closes, focus returns), Compare dialog (open/Esc/focus-trap), close-thesis modal (Esc). Assert focus management, not just visibility.

---

## Phase 3 — Close the route gaps (+ seed rungs)

### Task 3.1: New seed rungs

**Files:** Create `e2e/fixtures/seed_strategy.py`, `e2e/fixtures/seed_recall.py`, `e2e/fixtures/seed_book.py`, `e2e/fixtures/seed_predictions.py`; modify `e2e/conftest.py` (ladder edges) + `e2e/tests/test_seed_ladder.py`.

**Interfaces:**
- Produces fixtures `strategy`, `recall`, `book`, `predictions` (each depends on the right lower rung; idempotent; `_seed_lock()`-wrapped). Read each app's models first (`apps.strategy.{CoverageNote,CoverageRevision,RegimeReading,...}`, `apps.recall`, `apps.book.BookSnapshot`, `apps.observer.AIPrediction`).

- [ ] **Step 1.** For each rung: write `seed_<x>()` doing `get_or_create`/`update_or_create` keyed on stable names, producing the minimum objects each route needs to render populated. Follow `seed_observer.py`/`seed_triggers.py` as templates (PeriodicTask sync where relevant).
- [ ] **Step 2.** Wire fixtures into `conftest.py` with correct dependency edges; update the ladder docstring.
- [ ] **Step 3.** Extend `test_seed_ladder.py`: assert each new rung produces its documented objects + idempotency (writes to live DB via the unblock fixture).
- [ ] **Step 4: Run** `docker compose exec --workdir /app web uv run pytest e2e/tests/test_seed_ladder.py -v` → PASS.
- [ ] **Step 5: Commit.** `LEFTHOOK=0 git commit -am "test(e2e): seed rungs for strategy/recall/book/predictions"`

### Task 3.2: Route smoke + axe + visual per uncovered route (templated, ×17)

**Routes (from `frontend/src/router.tsx`):** `/settings/connections`, `/settings/system`, `/market-data`, `/snapshots`, `/scorecard`, `/mirror`, `/regime`, `/book`, `/themes`, `/warroom`, `/warroom/:id`, `/desk`, `/portfolio`, `/coverage/:ticker`, `/theses/new`, `/recall`, `/errors`.

> **Execution note:** This fans out to ~17 parallel subagents, one per route (worktree isolation NOT needed — distinct files). `/settings/connections` and `/theses/new` overlap Phase 2 flow tasks — coordinate so the smoke isn't duplicated (the flow test subsumes the smoke).

**Per-route template (read the page component first for landmarks/testids):**
- [ ] **a. POM** (if none): `e2e/pages/<route>.py` with `goto()` + landmark accessors.
- [ ] **b. ui smoke** in `e2e/ui/test_<route>.py`: navigate (highest seed rung needed), assert key landmark visible, assert `expect_error_boundary_absent()` (console-guard now catches router ErrorBoundary too).
- [ ] **c. axe**: add the route (with deterministic dynamic-id resolution via `order_by`) to `e2e/a11y/test_axe_per_route.py`.
- [ ] **d. visual**: add a parametrized baseline (light + dark) to `e2e/visual/test_route_snapshots.py`; generate with `make e2e-visual-update`, inspect the PNG, commit baseline.
- [ ] **e. Run** `make e2e-one t=ui/test_<route>.py` + the a11y/visual files → PASS; **commit** per route: `LEFTHOOK=0 git commit -am "test(e2e): cover /<route> (smoke + axe + visual)"`.

### Task 3.3: Broaden axe route list + dynamic-id determinism

**Files:** `e2e/a11y/test_axe_per_route.py`.
- [ ] Resolve `_resolve_path` model lookups with `order_by("id")` (not bare `.first()`); add the remaining secondary routes (`/market/:ticker`, `/settings`, `/costs/snapshot/:id`, etc.) to the scan list. Run → PASS. Commit.

---

## Phase 4 — Storybook coverage + MSW + a11y gate

### Task 4.1: Shared MSW handler module

**Files:** Create `frontend/src/__tests__/msw/handlers.ts` (or `.storybook/msw/handlers.ts`).
- [ ] Extract reusable handlers (quotes, positions, dashboard, analytics, costs, coverage, etc.) returning realistic fixtures, with `loading`/`error`/`empty` variants — mirror the `PositionsTable` story pattern. Run the existing storybook lane → still PASS. Commit.

### Task 4.2: Stories (templated, grouped)

> **Execution note:** fans out to parallel subagents grouped by directory. Each story: CSF3 meta with `args`/`argTypes`, ≥1 `play` with real assertions, MSW handlers for self-fetching components, both theme canvases where theme-sensitive. Read the component's props first.

- [ ] **4.2a Mandated primitives:** `ErrorBoundary`, `Toasts` (+ `ui/Toggle`).
- [ ] **4.2b Interactive:** `RuleBuilder` + `LeafRow` + `FiringsTable`, `CommandPalette`, `OptionChainTable`, `ToolCallTrace`, `QuoteCell`, `MarketStatusBadge`, `NotificationBell`.
- [ ] **4.2c Settings:** `settings/ProviderCard`, `ModelSelect`, `DataSourcesPanel`, `CapMeter`, `Field`, `SettingsSection`.
- [ ] **4.2d Data tiles (MSW):** `dashboard/*` tiles, `analytics/*` cards, `costs/*` charts, `thesis/ThesisBadges`, `RelatedObservations`, `BookTile`, `RegimeTile`, `DeskTile`, `MarketContextStrip`.
- [ ] **4.2e Thin-story upgrades:** add real `play` to `StopButton` (click → `onStop`) and `ThemeToggle` (cycle), and loading/error/empty to `WatchlistTable`.
- [ ] Each group: `docker compose exec frontend pnpm exec vitest --project storybook run` green → commit.

### Task 4.3: Promote a11y to gating

**Files:** `frontend/.storybook/preview.tsx` (+ per-story suppressions where needed).
- [ ] Change `a11y: { test: "todo" }` → `{ test: "error" }`. Run the full storybook lane; fix or per-story-suppress (documented reason) each violation. Add a light-theme assertion path for theme-sensitive stories. Run → PASS. Commit.

### Task 4.4: Story guard + Chromatic removal

**Files:** new guard (FE eslint rule or `frontend` meta-test listing high-value dirs); `frontend/.storybook/main.ts`; `frontend/package.json`.
- [ ] **a.** Add a check that fails when a component in a high-value dir (`components/`, `components/settings/`, `components/triggers/`, `components/dashboard/`, `components/analytics/`, `components/costs/`) has no `.stories.tsx`. Allow an explicit ignore list for intentional exclusions.
- [ ] **b.** Remove `@chromatic-com/storybook` from `main.ts` addons; drop `@chromatic-com/storybook` + `chromatic` from `package.json`; `pnpm install` to update the lockfile (on host, mind `minimumReleaseAge`). Run `pnpm run lint` + storybook lane. Commit.

---

## Phase 5 — CI wiring + harness hardening

### Task 5.1: e2e.yml → per-lane matrix

**Files:** `.github/workflows/e2e.yml`, `e2e/tests/test_gha_workflow.py`.
- [ ] **Step 1.** Refactor the single `ui` job into a matrix over lanes `[api, ui, ws, visual, a11y]` (each builds/reuses the e2e stack, runs its lane, tears down). Keep schemathesis + render-chart as their own steps/job. `ws` gets `continue-on-error: true` with a comment pointing at the Channels-delivery tracking note. `visual` + `a11y` are gates.
- [ ] **Step 2.** Update `test_gha_workflow.py` to assert EVERY lane + schemathesis + render-chart + teardown exists (not just `ui`). Run the meta-test (`E2E_SKIP_STACK_WAIT=1` in the `backend` job context) → PASS. Commit.

### Task 5.2: Fix the perf lane (advisory)

**Files:** `e2e/helpers/lighthouse_runner.py`, `e2e/perf/*`, `Makefile` (if target wiring changes), optional CI advisory job.
- [ ] Fix the runner: target the actually-served URL for the overlay it runs under; don't `docker exec ... frontend` from inside the container; add `--throttling-method=simulate` (or `devtools`) for representative numbers. Make the silent `pytest.skip` an explicit `xfail`/clear skip-reason only when lighthouse truly absent. If wired to CI, publish `median.json`/`.html` as an artifact with `continue-on-error` (advisory, never a gate). Run `make e2e-perf` locally → produces real numbers. Commit.

### Task 5.3: Harness meta-tests

**Files:** new `e2e/tests/test_scenario_handlers.py`, extend `e2e/tests/test_seed_ladder.py` (chain assertion).
- [ ] **a.** Assert every scenario in `apps/core/mocks/scenarios.py` SCENARIOS maps to a handler that is actually registered + distinct from the default fallback where a distinct behavior is intended (catch `handler_for` silent fallback to `stream_mocked_response`). Document scenarios that intentionally reuse the default.
- [ ] **b.** Assert the conftest seed-fixture dependency chain matches the documented ladder, including `thesis` as a side-branch off `threads`. Run both → PASS. Commit.

---

## Self-review

**Spec coverage:** Phase 0 ↔ spec §4 Phase 0 (✓ all 5 items). Phase 1 ↔ de-flake + pixel diff (✓). Phase 2 ↔ all 8 write-flows + keyboard overlays (✓). Phase 3 ↔ seed rungs + 17 routes + axe broadening (✓). Phase 4 ↔ stories + MSW + a11y gate + story guard + Chromatic removal (✓). Phase 5 ↔ CI matrix + perf + meta-tests + (a11y gate via Phase 4) (✓). Decisions §3: Chromatic removal (4.4b), perf advisory (5.2), ws continue-on-error (5.1), pixel diff (1.1) — all present.

**Placeholder scan:** Phase 0–1 carry full code/commands. Phases 2–5 are deliberately templated (DRY across ~17 routes / ~30 stories) with the per-item template spelled out and a "read the page/component first" instruction — the variable part (selectors/landmarks/props) is discovered at execution per the Global Constraints, not guessed here. No "TBD/handle edge cases" placeholders.

**Type consistency:** `capture_or_compare(..., max_diff_ratio=0.001)` (1.1) used consistently; `wait_ready`/`wait_for_app_ready` (1.2) referenced in 1.2/3.2; POM method names (`SnapshotPage.capture/wait_for_complete/send_to_ai`, `TriggerEditorPage.fill_simple/fill_dsl/save`, `SchedulesPage.create/run_now`, `CostsPage.set_caps`) match the audit's POM inventory.
