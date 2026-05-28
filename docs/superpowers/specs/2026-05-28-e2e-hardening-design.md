# E2E suite hardening — design

**Date:** 2026-05-28
**Status:** approved-pending-review
**Scope:** test-quality work on the existing six-lane E2E suite (`e2e/`). No product/backend behavior changes (genuine product gaps are flagged, not fixed).

## Problem

The E2E suite is broad (six lanes, ~70 test files) and green, but "green" does not currently mean "tested." Two systemic weaknesses, both previously observed when the suite failed to catch egregious chat-flow bugs ("Send did nothing" / "Response never rendered"):

1. **Assertion-free UI tests.** ~40 assertions across 13 of ~18 UI test files assert only `expect(page.locator("body")).to_be_visible()`. That is true for *any* HTML, including a crashed React error-boundary page. Test *names* promise behavior (`csv_export_downloads_and_parses`, `caps_editor_persists`, `structured_mode_produces_typed_card`) the bodies never verify.
2. **Silent skips.** ~20 in-body `pytest.skip(...)` calls turn "feature missing" or "data not seeded" into a green pass. At runtime only 6 actually fire (see baseline); the rest are **dead guards** whose conditions are always satisfied — noise that hides which skips are real.

Plus two confirmed coverage holes and a flakiness-under-load signal (below).

## Baseline (captured 2026-05-28, isolated worktree stack, `-n 2`)

Clean run (no cross-lane contention):

| Lane    | Result                  | Notes |
|---------|-------------------------|-------|
| UI      | 56 passed, 4 skipped    | 24 min wall (`-n 2`) |
| API+WS  | 47 passed, 2 skipped    | 45 min wall (`-n 2`) |
| Visual  | not re-run              | baselines committed; assumed green, verified in Phase 3 |
| A11y    | not re-run              | assumed green, verified in Phase 3 |

**Total: 103 passed, 6 skipped, 0 real failures.**

The 6 runtime skips:
- `api/test_scenario_engine_disabled_in_prod.py` ×2 — prod-posture-only; **legitimate, keep.**
- `ui/test_error_paths.py:55` — no provider-`enabled` gate in the AI run path (backend gap).
- `ui/test_error_paths.py:78` — cap-exceeded `_fail()` renders without `message_started` (backend gap).
- `ui/test_observer.py:61` — observer cost-cap system message not surfaced on `/threads/observer/<id>`.
- `ui/test_analytics.py:59` — ticker input not present on `/analytics`.

**Flakiness signal:** running UI + API/WS concurrently produced one failure — `ws/test_notifications.py::test_notifications_observer_done_delivered` timed out after 30 s waiting for `notification.event` post `run-now`. It **passes in isolation** (3/3, 108 s). Root cause: worker saturation + a too-tight 30 s timeout. This is a Phase-4 target, not a product bug.

## Non-goals

- No changes to product/backend behavior. The two `test_error_paths.py` backend gaps and any other genuine product defects are converted to tracked `xfail` and reported, not fixed in this work.
- No new test lanes or harness rewrites. We use the existing lanes, page objects, fixtures, and scenario engine.
- Perf lane (Lighthouse, prod overlay) is out of scope.

## Approach

Four phases, each an independently committable unit, sequenced highest-signal-first. The enabling fact: **page objects are already rich (8–15 methods each) and `e2e/ui/test_threads.py` already establishes the gold-standard pattern.** Most Phase-1 work is wiring existing page-object methods and asserting real outcomes — not building new infrastructure.

### Phase 1 — Harden weak UI assertions

Replace every `expect(body).to_be_visible()` smoke check with a behavioral assertion, following the `test_threads.py` pattern: *drive the real action → wait for the real signal → assert real content/state.*

Target files (body-only assertion count): `analytics` (6), `triggers` (5), `snapshots` (5), `observer` (5), `costs` (3), `watchlists` (3), `files_and_citations` (3), `settings` (2), `compare` (2), `profiles` (2), `schwab_oauth` (2), `dashboard` (1), `error_paths` (1).

Concrete examples:
- `costs::caps_editor_persists` → `set_caps(daily, monthly)`, reload, assert the values persisted.
- `costs::csv_export_downloads_and_parses` → `export_csv()`, assert bytes parse as CSV with the expected header row.
- `observer::structured_mode_produces_typed_card` → assert the typed observation card renders (not just `<body>`).
- `snapshots::capture_partial_failure_marks_sections` (scenario `news-503`) → assert the news section shows a failed state.

A test with no honest UI surface to assert is escalated to Phase 2 (not left body-only). Where a page object lacks a needed selector/method, add it to the page object (the only "new infrastructure" permitted in this phase).

**Done when:** zero `expect(body).to_be_visible()`-only test bodies remain in `e2e/ui/`, and each hardened test asserts a behavior its name promises.

### Phase 2 — Triage every skip

Classify each `pytest.skip(...)` into one of four buckets and act:

- **Legitimate** (prod-posture): the 2 `scenario_engine_disabled_in_prod` skips — keep as-is.
- **Dead guard** (condition never fires at runtime, e.g. `snapshots` diff "≥2 ready" — the seed yields 4): **remove the guard**, the test always runs.
- **Infra-fixable** (seed/fixture/scenario gap): fix the seed or fixture so the test runs for real (e.g. `analytics` ticker input, `observer` cost-cap message — verify whether the surface exists and the seed feeds it).
- **Genuine product gap** (no honest surface exists; backend defect): convert silent `skip` → `xfail(reason=..., strict=False)` so it is tracked and auto-flips to XPASS when the product is fixed. **The two `test_error_paths.py` backend-gap skips are the primary candidates** — but first re-verify against current `origin/main` code (`apps/ai/router.py`, `apps/threads/tasks.py:_fail`, `ThreadDetailPage.onWs`), since a prior PR may have fixed them, in which case they become un-skippable, not xfail.

**Done when:** every skip is one of {legitimate-keep, removed-dead-guard, now-running, tracked-xfail}; no skip silently masks a coverage hole. A short table of genuine product gaps is produced for the user to prioritize separately.

### Phase 3 — Add coverage for untested flows

Confirmed gaps:
- **`/briefing`** (Morning Briefing, `apps.briefing`): zero coverage across UI, API, and WS lanes.
- **`/events`** (Market Events): no UI test (API `market` contract may partially cover events — verify and extend if not).

Follow the README "Adding a new feature" recipe: UI gold test + API contract test + WS test if the feature emits a WS event + visual baseline + a11y check. Add a page object for `/briefing` if none exists. Re-run visual + a11y lanes here to confirm the assumed-green baseline and capture new-route baselines.

**Done when:** `/briefing` has UI + API (+ WS if applicable) gold tests; `/events` has a UI gold test; new routes have visual baselines and pass a11y.

### Phase 4 — Flake audit + stabilize

- Run `tools/flake_audit.py` (re-runs each lane 3×) and address the worst offenders.
- Fix the known `test_notifications_observer_done_delivered` flake: widen the notification wait timeout and/or make the assertion robust to worker latency (it passes in isolation but fails under load).
- Address the documented cross-lane DB-truncation interactions (`test_seed_ladder.py` vs `api/`) where a cheap fix exists.

**Done when:** `flake_audit.json` shows no test below a stable pass ratio across 3× reruns, and the notifications flake is fixed.

## Sequencing & validation

1 → 2 → 3 → 4. Each phase is committed separately (`test(e2e):` / `fix(e2e):`). After each phase, run the affected lane(s) on the isolated worktree stack to confirm green (single-file `make e2e-one` during iteration — the full UI lane is ~24 min, so do not run it per-edit). A final full `make e2e` run validates the complete suite before hand-off.

## Risks

- **Slow lanes.** UI 24 min, API+WS 45 min under `-n 2`. Mitigation: iterate per-file with `make e2e-one`; reserve full-lane runs for phase boundaries.
- **Shared-DB contention** produces false failures when lanes run concurrently (observed). Mitigation: run one lane at a time on the worktree stack; CI already isolates.
- **Hardened assertions may surface real product bugs** (the point). Per non-goals, those become tracked `xfail` + a flagged report, not in-scope fixes — keeps this work bounded to tests.
