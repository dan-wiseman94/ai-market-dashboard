# E2E test suite

Six-lane comprehensive suite. Full design: `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md`.

## Lane layout

| Lane     | Dir               | What it tests                               | Container  | Run locally          |
|----------|-------------------|---------------------------------------------|------------|----------------------|
| UI       | `e2e/ui/`         | Playwright browser journeys                 | `worker`   | `make e2e-ui`        |
| API      | `e2e/api/`        | httpx contract against DRF endpoints        | `web`      | `make e2e-api`       |
| WS       | `e2e/ws/`         | Channels WebSocket event assertions         | `web`      | `make e2e-ws`        |
| Visual   | `e2e/visual/`     | Page-level screenshot diffs                 | `worker`   | `make e2e-visual`    |
| A11y     | `e2e/a11y/`       | axe-core scans per route + keyboard-only    | `worker`   | `make e2e-a11y`      |
| Perf     | `e2e/perf/`       | Playwright LCP/CLS/TBT budgets (prod overlay) | `worker` | `make e2e-perf`      |

`make e2e` runs ui/api/ws/visual/a11y together. Perf is separate because it
needs the prod overlay.

**Why the worker?** The chromium playwright build is in the worker image (added
for the chart-render Celery task). The UI / visual / a11y lanes exec inside the
worker so they share the same browser binary.

## Workflow

```
# First time
make e2e-up                              # build + start stack with overlay

# Iterate
make e2e-one t=ui/test_snapshots.py
HEADED=1 make e2e-one t=ui/test_snapshots.py   # visual debug

# Update visual baselines
make e2e-visual-update
git diff e2e/visual/__screenshots__/

# Tear down
make e2e-down
```

## Updating visual baselines

When UI changes are intentional:

```
make e2e-visual-update
git diff e2e/visual/__screenshots__/
git add e2e/visual/__screenshots__/
git commit -m "chore(e2e/visual): update baselines for <what changed>"
```

A PR that changes baselines **must** include a visual-diff summary in the PR
description. Reviewers should open a handful of before/after PNGs.

Baselines are capped at 600KB each — `tools/hooks/check_visual_baseline_size.sh`
blocks oversized ones at pre-commit (and `e2e/tests/test_baseline_size_guard.py`
in CI). If you hit the cap, the problem is usually a mask leak; check that noisy
dynamic regions (timestamps, chart tooltips, notification counts) are masked in
`helpers/visual.py`.

## Known limitations

- **Visual lane uses byte-level diff.** Playwright Python doesn't ship a
  `to_have_screenshot()` assertion the way Playwright Test (Node) does, so we
  roll our own `helpers/visual.capture_or_compare`. Any byte change between
  the new screenshot and the baseline fails the test. This is fine for
  most routes once dynamic regions are masked but breaks down on `/costs`
  where seeded AIRun amounts are random and bleed into multiple cells.
  `/costs` is intentionally excluded from the parametrized list; bring it
  back once we wire a pixel-tolerance diff library (pixelmatch-py or PIL).
  `/briefing` and `/events` are captured in their **empty** states (the
  `minimal` rung has no `BriefingRun` / `MarketEvent` rows) to stay byte-stable.
- **Multi-provider compare under `MOCK_EXTERNAL`.** All three providers
  short-circuit to a canned stream, so claude + openai branches both run. But
  the compare dialog's provider `<select>` only offers providers that have
  **catalog models**, and the e2e seed registers only claude + openai (no
  `local` models) — so the compare tests fan out across those two, not a literal
  three-provider spread.
- **`tools/flake_audit.py` doesn't pass `-p`.** It runs `docker compose exec`
  against the **default** project, so locally it targets the dev `ai-dashboard`
  stack, not your e2e stack. Run it with `-p <checkout>-e2e` (or rely on the
  nightly CI run, which has a single stack).
- **Some failures render racily.** A no-stream `_fail(event="error")` (e.g.
  provider-disabled) returns in ~20 ms and can lose the UI render race (the error
  path doesn't refetch); `test_provider_disabled_blocks_send` asserts the gate at
  the DB layer instead. The `cost_capped` path renders reliably.

## Known test interactions

- **Don't mix `e2e/tests/test_seed_ladder.py` with `e2e/api/` in a single pytest
  invocation.** The seed-ladder tests use ``@pytest.mark.django_db(transaction=True)``
  which truncates the live DB at end-of-test; the api lane relies on data the
  seed fixtures wrote moments earlier. Run them in separate invocations
  (Make targets do this automatically).
- **Detail-endpoint API tests (snapshot/thread/trigger) require fresh seeds.**
  They retrieve an object ID via Django ORM, then hit the API for that ID. If
  the live DB was truncated by a previous test, the ORM still sees the row
  (cached connection state) but the API returns 404. Re-run the api lane after
  any teardown.

## Troubleshooting matrix

| Symptom                                      | Likely cause                                          | Fix                                                       |
|----------------------------------------------|-------------------------------------------------------|-----------------------------------------------------------|
| `ui` test fails with "CONSOLE" error         | JS error in the frontend                              | Fix it. Add to `ALLOWED_CONSOLE_PATTERNS` only if benign. |
| `visual` test fails with masked region       | New dynamic region rendered outside mask              | Add it to `default_masks()` in `helpers/visual.py`.       |
| `a11y` axe violation on new page             | Missing aria-label / heading / focus style            | Fix the DOM. Don't add to `a11y_ignores` without an issue link. |
| `perf` LCP over budget                       | Blocking JS / large image on critical path            | Check `e2e/perf/artifacts/<route>/median.html`; budgets in `budgets.json`. |
| `ws` test hangs                              | Backend not producing the event or wrong scenario     | Inspect `docker compose logs web worker`.                 |
| "Mocked response" appears in a non-mock test | E2E overlay left running                              | `make e2e-down`.                                          |
| Visual baseline missing                      | First run on this route                               | Create with `make e2e-visual-update`; commit new PNGs.    |
| New test failing only in CI                  | Likely timing/flake                                   | Check `flake_audit.json` on latest main.                  |

## When to open an issue vs. fix in-flight

- Single flaky-looking failure on a never-flaky test: rerun once, then open issue if it recurs.
- Baseline drift after unrelated change: investigate; don't blindly update baselines.
- New a11y violation introduced by your branch: fix it in your branch.
- Perf-budget regression > 10% on a route: block the PR; do not bump the budget without rationale.

## Adding a new feature

1. Add a UI gold test to the appropriate `e2e/ui/test_<feature>.py`.
2. Add an API contract test to `e2e/api/test_<feature>_contract.py`.
3. If the feature introduces a WS event, add a `e2e/ws/test_<feature>.py` test.
4. Capture a visual baseline: `make e2e-visual-update`.
5. Run `make e2e-a11y` to confirm no new violations.
6. If the route is new + non-trivial, add it to `e2e/perf/budgets.json` (`test_perf_budgets.py` parametrizes over it).

## Scenario engine cheat sheet

```python
def test_something(page, frontend_base_url, minimal, scenario):
    scenario.use("claude-5xx-midstream")
    # ... subsequent actions carry the X-E2E-Scenario header ...
```

Available scenarios (see `backend/apps/core/mocks/scenarios.py` for the full
registry):

| Scenario                  | Effect on Claude                                 | Other services           |
|---------------------------|--------------------------------------------------|--------------------------|
| `default`                 | Streams "Mocked response"                        | All ok                   |
| `claude-5xx`              | 503 pre-stream                                   | All ok                   |
| `claude-5xx-midstream`    | 2 deltas then error                              | All ok                   |
| `claude-ratelimit`        | 429 retry-after=30                               | All ok                   |
| `openai-timeout`          | (default)                                        | openai hangs 60s         |
| `schwab-401`              | (default)                                        | schwab 401 token expired |
| `schwab-oauth-ok`         | (default)                                        | schwab full oauth flow   |
| `news-503`                | (default)                                        | finnhub 503              |
| `cap-exceeded`            | (default — intercepted in cost.py)               | All ok                   |
| `files-upload-fail`       | (default)                                        | files 500 on upload      |
| `tool-use-loop`           | tool_call → tool_result → text                   | All ok                   |
| `thinking-heavy`          | thinking_delta*  → text_delta* → done            | All ok                   |
| `structured-observation`  | ObservationReport-shaped JSON                    | All ok                   |

Adding a new scenario: insert an entry in `apps/core/mocks/scenarios.py` and a
handler in `apps/core/mocks/providers.py` (then wire it into the per-provider
adapter under `apps/ai/providers/`).

## Flake audit

`tools/flake_audit.py` re-runs every lane 3× and writes `flake_audit.json` with
per-test pass/fail ratios. The nightly `.github/workflows/flake-audit.yml`
Action runs it and (on Mondays) opens a weekly issue listing the top-10 flakiest
tests.

## CI surface

`.github/workflows/e2e.yml` runs on PRs, merges to `main`, and manual dispatch.
A single job builds the e2e stack (`compose.e2e.yaml`) and runs the lanes in
sequence — api, schemathesis fuzz, the `/render/chart` chromium test, ui, a11y,
ws — then tears down (`down -v`). **Visual and perf are off the PR gate** (visual
needs committed byte-diff baselines, perf budgets are calibrated for the prod
overlay, not the CI dev build); run those via `make e2e` locally or on merge. On failure, Playwright traces upload as the
`ui-traces` artifact (`--tracing=retain-on-failure`, 7-day retention).
