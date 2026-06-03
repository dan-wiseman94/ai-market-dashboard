# Quality & Correctness Tooling Rollout

**Written 2026-06-03.** Thirteen additions to the quality stack, hard-gated in CI.
The repo already runs ruff, ty (advisory), pytest (+cov/xdist/asyncio), vitest,
eslint+tsc, Storybook+a11y, a six-lane Playwright E2E suite, semgrep,
pip-audit/pnpm-audit/Dependabot, lefthook hooks, and a nightly flake audit. This
spec covers what's *missing*.

## The throughline

This codebase encodes its real risks as prose **landmines** in `CLAUDE.md` —
import cycles (`apps.threads → apps.thesis`), the `*_id` serializer-key contract,
"go through `decrypt_token`", "don't instantiate providers directly", section
`"done"` vs snapshot `"ready"`. A reviewer remembering a comment is the only thing
enforcing them. The highest-leverage tools here **convert those prose warnings
into executable gates** so a future change *cannot* reintroduce the bug a comment
warns about.

## Decisions locked (from brainstorming, 2026-06-03)

1. **Hard-gate everything.** Each new check must *pass*, not merely run — these are
   real CI gates, not advisory like the existing `ty` / `pip-audit`
   (`continue-on-error`) steps.
2. **mypy + django-stubs, keeping ty.** ty stays in lefthook for fast local
   feedback; mypy is the thorough, ORM-aware CI checker.
3. **Sentry off by default** via an empty `SENTRY_DSN` (complete no-op until opted
   in). Localhost single-user app; nothing phones home unprompted.

### Two ratchets (approved)

A literal "fix every pre-existing violation now" is reckless on two surfaces
(~26k LOC / 357 backend files; 481 frontend TS interfaces). For these, the *real
gate* is a ratchet — new violations fail CI; the legacy backlog is recorded, not
rewritten in one pass:

- **mypy** via `mypy-baseline`: today's errors captured into a committed
  `mypy-baseline.txt`; CI fails on any *new* error. The high-value core
  (`apps/ai/cost.py`, `catalog.py`, `token_counter.py`,
  `apps/snapshots/token_budget.py`, `apps/market/returns.py`) is fixed by hand and
  removed from the baseline in this pass.
- **openapi-typescript**: generate `frontend/src/api/schema.d.ts` + a CI drift
  gate; adopt the generated types incrementally (the `*_id` contract surface
  first). The 481 hand-written interfaces are **not** rewritten now.

## Shared principles

- **Gate placement mirrors the existing split.** Backend gates land in
  `.github/workflows/check.yml` (`backend` job) and `Makefile` (`lint` / new
  targets); frontend gates in the `frontend` job + `package.json` scripts; fast
  per-file checks in `lefthook.yml`. Slow/periodic checks (mutation) get their own
  scheduled workflow, like `flake-audit.yml`.
- **All tool config in `pyproject.toml`** (the repo's existing rule — no standalone
  `mypy.ini` etc.) except where a tool mandates its own file (`.importlinter`,
  `.gitleaks.toml`).
- **`uv.lock` / `pnpm-lock.yaml` are committed** — every dependency add is
  `uv lock` / `pnpm install` then commit the lockfile; Docker/CI use `--frozen`.
- **Everything runs in Docker.** Local invocations are `docker compose exec`; CI
  runs bare-runner equivalents already established in `check.yml`.
- **Definition of done is evidence, not assertion.** Each new gate is demonstrated
  failing on a deliberate violation, then passing once fixed. `make check` green
  before a phase is considered complete.

---

## Workstream 1 — Quick clean gates (fix-all-now, block CI)

- **`makemigrations --check --dry-run`** — new step in the `backend` CI job and a
  `make check-migrations` target. Fails on model/migration drift. Fix: generate
  any missing migration (`migration-reviewer` conventions apply — reversible, no
  destructive/locking ops).
- **import-linter** — `.importlinter` with contracts from the documented landmines:
  - *forbidden:* `apps.threads` → `apps.thesis` (the `DecisionJournalEntry`
    cycle).
  - *forbidden:* `apps.*.views` / `apps.*.tasks` → `apps.ai.providers` (must route
    through `apps.ai.router` / `get_provider()`).
  - *forbidden:* any module except `apps.secrets.credentials` doing the raw token
    decrypt (reads go through `decrypt_token`).
  - New `lint-imports` CI step + `make lint-imports`. I fix any real current
    violations (expected few).
- **gitleaks** — pre-commit command in `lefthook.yml` + a CI job; `.gitleaks.toml`
  allowlists `.env.example` and test fixtures. Blocks on any committed secret.
- **pytest-randomly + pytest-timeout** — dev-deps + `addopts` (`--timeout=60`,
  randomly is automatic). Surfaces order-dependent flakes and hangs; I fix any that
  appear (complements the existing flake audit).

## Workstream 2 — Type checking (mypy + django-stubs; keep ty)

- Dev-deps: `mypy`, `django-stubs[compatible-mypy]`,
  `djangorestframework-stubs`, `mypy-baseline`.
- `[tool.mypy]` in `pyproject.toml` + `mypy_django_plugin` with
  `django_settings_module = "config.settings.dev"`; exclude `migrations`.
- CI step: `mypy backend | mypy-baseline filter` (fails on new errors only).
  `mypy-baseline.txt` committed.
- Hand-fix + baseline-shrink the money/core modules listed above.
- ty stays exactly as-is in lefthook (fast local advisory).

## Workstream 3 — API contract (drf-spectacular → schemathesis → openapi-typescript)

- **drf-spectacular** — add to `INSTALLED_APPS` + `DEFAULT_SCHEMA_CLASS`; generate
  `backend/schema.yml`. CI step regenerates and `git diff --exit-code`s it (drift
  gate). Resolve any spectacular warnings on the 46 view classes.
- **schemathesis** — new `e2e/api` (or `backend` integration) lane fuzzing every
  endpoint against the schema for 500s / contract violations. Hard-gate; if a large
  pre-existing set surfaces, baseline them (documented `xfail` list) and gate new —
  same ratchet logic, recorded honestly.
- **openapi-typescript** — `pnpm` dev-dep; generate `frontend/src/api/schema.d.ts`;
  `pnpm gen:api` script + CI drift check. Adopt generated types for the
  highest-churn contract types (the `*_id` landmine surface). No mass rewrite.

## Workstream 4 — Runtime / test correctness

- **Hypothesis** (property-based testing) — dev-dep + property tests over the
  pure-logic units `CLAUDE.md` names: the trigger condition DSL
  (`apps.triggers` evaluator/parser — nested `all/any/not`), payload token
  trimming (`apps.snapshots.token_budget`), cost calc (`apps.ai.cost` against
  `catalog`), and market-hours (`apps.observer.services.market_hours`). These are
  characterization/property tests of existing functions; additive and low-risk.
  Blocks (new tests must pass).
- **nplusone** — enabled in a test-only settings path (raises on N+1 in tests). I
  fix N+1s it finds in the aggregation-heavy endpoints (`apps.analytics`,
  `apps.dashboard`, leaderboard). Blocks.
- **Coverage gating** — backend `--cov-fail-under=<current>` in `pyproject`
  `addopts`; frontend vitest `coverage.thresholds` at current measured level.
  Ratchet-up later. Blocks on regression.
- **mutmut** — config + `make mutate` + a nightly workflow (mirrors
  `flake-audit.yml`) scoped to the money paths (`apps/ai/cost.py`, cap checks,
  `apps/thesis/services/postmortem.py::objective_verdict`). **Not** a PR gate —
  too slow; nightly report only.

## Workstream 5 — Error visibility

- **Sentry** — `sentry-sdk` (django + celery integrations), initialized in
  `config/settings/base.py` *only when* `SENTRY_DSN` is set (empty default →
  no-op). A `before_send`/explicit-capture hook at the `_safe()` / warn-and-continue
  swallow points (dashboard rollup, briefing assemble, coverage revise, postmortem
  narrative) so silent degradation becomes visible **when opted in**. No DSN
  committed; nothing transmitted by default.

## Execution strategy

**Phased conventional commits on `chore/quality-tooling`**, in the order above —
each phase ends with the relevant `make` subset green before the next. Rejected
alternatives: one big PR (unreviewable, high CI blast radius); parallel
worktrees/subagents (every workstream edits the same shared files —
`pyproject.toml`, `check.yml`, `Makefile`, `lefthook.yml` — so parallelism only
creates conflicts).

Phase order: WS1 (quick gates) → WS2 (mypy) → WS3 (API contract) → WS4 (test
correctness) → WS5 (Sentry). Dependency reason: schemathesis (WS3) needs the
drf-spectacular schema; everything else is independent but sequenced for clean
review.

## Out of scope (YAGNI)

- Rewriting all 481 frontend interfaces onto generated types (incremental only).
- Fixing all ~thousands of mypy errors (baseline + core only).
- bandit / CodeQL (semgrep `p/security-audit` already covers SAST).
- Dependency-update automation (Dependabot already configured).
- Replacing ty (kept for fast local feedback, per decision 2).

## Verification / definition of done

1. `make check` green locally on the branch.
2. Each new gate shown failing on a deliberate violation, then green once fixed
   (evidence captured in the relevant phase commit message / PR body).
3. `make e2e` unaffected (new lanes pass under the e2e overlay where applicable).
4. CLAUDE.md updated: new `make` targets in the daily-commands table; the new
   gates noted in the testing/landmines sections.
