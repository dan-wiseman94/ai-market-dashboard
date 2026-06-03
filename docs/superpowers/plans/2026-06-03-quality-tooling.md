# Quality & Correctness Tooling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 13 hard-gated quality/correctness checks to the existing stack, converting CLAUDE.md's prose "landmines" into executable CI gates.

**Architecture:** Five phases on branch `chore/quality-tooling`, sequential conventional commits. Backend gates land in `.github/workflows/check.yml` + `Makefile`; frontend gates in the `frontend` CI job + `package.json`/`vite.config.ts`; per-file checks in `lefthook.yml`; slow checks (mutation) in a new scheduled workflow. mypy and the frontend type surface are landed as ratchets (gate new violations; baseline the legacy backlog).

**Tech Stack:** import-linter, mypy + django-stubs + mypy-baseline, drf-spectacular, schemathesis, openapi-typescript, Hypothesis, nplusone, coverage (pytest-cov/v8), mutmut, gitleaks, pytest-randomly, pytest-timeout, sentry-sdk.

**Spec:** `docs/superpowers/specs/2026-06-03-quality-tooling-design.md`

**Cross-cutting rules (apply to every task):**
- Everything runs in Docker. Local backend cmds: `docker compose exec -w /app/backend web uv run <cmd>` (container WORKDIR is `/app/backend`). Frontend: `docker compose exec frontend pnpm <cmd>`. Bring the stack up first: `make up`.
- After adding a Python dep to `pyproject.toml`, run `uv lock` (host) and commit `uv.lock`; rebuild the image or `docker compose exec web uv sync --frozen --dev`. After a frontend dep, `pnpm install` updates `pnpm-lock.yaml` — commit it.
- These are real libraries with evolving flags. **Before configuring each tool, verify current config/CLI via context7** (`resolve-library-id` → `query-docs`) — the config blocks below are correct as of writing but confirm syntax (esp. import-linter wildcards, django-stubs plugin name, schemathesis CLI, mypy-baseline subcommands).
- Each gate must be demonstrated: introduce a deliberate violation, watch the gate fail, revert, watch it pass. Capture that in the commit body.

---

## File Structure

**Created:**
- `.gitleaks.toml` — secret-scan rules + allowlist (`.env.example`, fixtures)
- `mypy-baseline.txt` — recorded legacy mypy errors (ratchet)
- `backend/schema.yml` — generated OpenAPI schema (committed; drift-gated)
- `backend/config/settings/test.py` — test settings (imports dev, adds nplusone)
- `frontend/src/api/schema.d.ts` — generated TS types (committed; drift-gated)
- `e2e/api/test_schemathesis.py` — schema fuzz lane
- `backend/apps/triggers/tests/test_dsl_properties.py` — Hypothesis: DSL evaluator
- `backend/apps/snapshots/tests/test_token_budget_properties.py` — Hypothesis: trimming
- `backend/apps/ai/tests/test_cost_properties.py` — Hypothesis: cost calc
- `backend/apps/observer/tests/test_market_hours_properties.py` — Hypothesis: market hours
- `.github/workflows/mutation.yml` — nightly mutmut report

**Modified:**
- `pyproject.toml` — dev-deps; main-deps (`drf-spectacular`, `sentry-sdk`); `[tool.mypy]`, `[tool.django-stubs]`, `[tool.importlinter]`, `[tool.mutmut]`, `[tool.coverage.report]`; pytest `addopts` (`--timeout`), `DJANGO_SETTINGS_MODULE` → `config.settings.test`
- `Makefile` — targets `check-migrations`, `lint-imports`, `typecheck`, `schema`, `gen-api`, `mutate`; wire into `lint`
- `.github/workflows/check.yml` — steps for the above gates
- `lefthook.yml` — gitleaks pre-commit; lint-imports pre-push
- `frontend/package.json` — devDep `openapi-typescript`; scripts `gen:api`
- `frontend/vite.config.ts` — vitest coverage thresholds
- `backend/config/settings/base.py` — drf-spectacular (INSTALLED_APPS + `DEFAULT_SCHEMA_CLASS` + `SPECTACULAR_SETTINGS`); Sentry init (env-gated)
- `backend/config/urls.py` — `SpectacularAPIView` route (respect include-ordering landmine)
- `.env.example` — document `SENTRY_DSN`
- `CLAUDE.md` — new `make` targets + gates in testing/landmines sections

---

# PHASE 1 — Quick clean gates (WS1)

## Task 1: pytest-randomly + pytest-timeout

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: Add dev-deps.** In `[dependency-groups].dev` add:
```toml
    "pytest-randomly>=3.16,<4.0",
    "pytest-timeout>=2.4,<3.0",
    "hypothesis>=6.140,<7.0",
```
(Hypothesis added now; used in Task 9.)

- [ ] **Step 2: Add a per-test timeout.** In `[tool.pytest.ini_options]`, change `addopts` to append `--timeout=60`:
```toml
addopts = "-ra --strict-markers --tb=short -m 'not integration' --timeout=60"
```

- [ ] **Step 3: Lock + sync.**
Run: `uv lock && docker compose exec web uv sync --frozen --dev`
Expected: lockfile updates; sync succeeds.

- [ ] **Step 4: Run the suite (randomized order + timeout active).**
Run: `docker compose exec -w /app/backend web uv run pytest -q`
Expected: header shows `Using --randomly-seed=...`; suite passes. If a test now fails ONLY under reordering, it has hidden inter-test state — fix it (e.g. missing DB rollback, module-global mutation). Re-run until green.

- [ ] **Step 5: Commit.**
```bash
git add pyproject.toml uv.lock
git commit -m "test: randomize test order + 60s per-test timeout (pytest-randomly/timeout)"
```

## Task 2: makemigrations --check gate

**Files:** Modify `Makefile`, `.github/workflows/check.yml`

- [ ] **Step 1: Add a Makefile target.** After the `migrate` target:
```make
.PHONY: check-migrations
check-migrations: ## Fail if models changed without a migration
	$(COMPOSE) exec -w /app/backend web uv run python manage.py makemigrations --check --dry-run
```

- [ ] **Step 2: Verify current tree is clean.**
Run: `make check-migrations`
Expected: `No changes detected` and exit 0. If it reports missing migrations, run `make makemigrations`, review (reversible, no destructive/locking ops per `migration-reviewer`), and commit them separately first.

- [ ] **Step 3: Add the CI step.** In `.github/workflows/check.yml`, `backend` job, immediately before the `pytest` step:
```yaml
      - name: makemigrations --check (model/migration drift)
        run: uv run python backend/manage.py makemigrations --check --dry-run
```

- [ ] **Step 4: Demonstrate the gate.** Add a throwaway field to any model, run `make check-migrations`, confirm it exits non-zero (`Your models ... have changes not yet reflected in a migration`), then revert the field.

- [ ] **Step 5: Commit.**
```bash
git add Makefile .github/workflows/check.yml
git commit -m "ci: gate on missing migrations (makemigrations --check)"
```

## Task 3: import-linter (the landmine gate)

**Files:** Modify `pyproject.toml`, `Makefile`, `.github/workflows/check.yml`, `lefthook.yml`

- [ ] **Step 1: Verify config syntax via context7** (`import-linter`) — confirm `[tool.importlinter]` pyproject support and the wildcard syntax for `source_modules` in forbidden contracts.

- [ ] **Step 2: Add dev-dep.** In `[dependency-groups].dev`: `"import-linter>=2.5,<3.0",`

- [ ] **Step 3: Add contracts to `pyproject.toml`:**
```toml
[tool.importlinter]
root_packages = ["apps"]

[[tool.importlinter.contracts]]
name = "threads must not import thesis (DecisionJournalEntry cycle)"
type = "forbidden"
source_modules = ["apps.threads"]
forbidden_modules = ["apps.thesis"]

[[tool.importlinter.contracts]]
name = "providers reached only via ai.router (not instantiated in views/tasks)"
type = "forbidden"
source_modules = ["apps.threads.views", "apps.observer.services.run", "apps.triggers.tasks"]
forbidden_modules = ["apps.ai.providers"]
allow_indirect_imports = true

[[tool.importlinter.contracts]]
name = "encrypted tokens decrypted only in apps.secrets.credentials"
type = "forbidden"
source_modules = ["apps.market", "apps.ai", "apps.threads", "apps.observer"]
forbidden_modules = ["cryptography.fernet"]
allow_indirect_imports = true
```
(Adjust `source_modules` lists to the real importers found in Step 5.)

- [ ] **Step 4: Makefile target.** After `lint-backend`:
```make
.PHONY: lint-imports
lint-imports: ## Enforce architecture import contracts
	$(COMPOSE) exec -w /app/backend web uv run lint-imports
```

- [ ] **Step 5: Run + fix real violations.**
Run: `make lint-imports`
Expected: `Contracts: N kept, 0 broken.` If a contract breaks, either the code has a real violation (fix it — e.g. route a direct provider import through `apps.ai.router.get_provider`) or the contract is mis-scoped (tighten `source_modules`). Iterate to green.

- [ ] **Step 6: Wire into `lint` + CI + pre-push.**
In `Makefile`, change `lint-backend` to also run imports, OR add `lint-imports` to the `lint` aggregate:
```make
lint: lint-backend lint-imports lint-frontend ## Lint everything
```
In `check.yml` `backend` job, after `ruff format --check`:
```yaml
      - name: import-linter (architecture contracts)
        run: cd backend && uv run lint-imports
```
In `lefthook.yml` `pre-push`, add a command:
```yaml
    import-contracts:
      run: docker compose exec -T -w /app/backend web uv run lint-imports
```

- [ ] **Step 7: Demonstrate.** Add `import apps.thesis` to a module in `apps/threads/`, run `make lint-imports`, confirm the contract breaks, revert.

- [ ] **Step 8: Commit.**
```bash
git add pyproject.toml Makefile .github/workflows/check.yml lefthook.yml uv.lock
git commit -m "ci: enforce architecture import contracts (import-linter)"
```

## Task 4: gitleaks (secret scanning)

**Files:** Create `.gitleaks.toml`; Modify `lefthook.yml`, `.github/workflows/check.yml`

- [ ] **Step 1: Verify config via context7** (`gitleaks`) — confirm `.gitleaks.toml` `[extend] useDefault = true` + `[allowlist]` schema for the installed version.

- [ ] **Step 2: Create `.gitleaks.toml`:**
```toml
title = "ledger gitleaks config"

[extend]
useDefault = true

[allowlist]
description = "Non-secret template + test fixtures"
paths = [
  '''\.env\.example$''',
  '''.*/tests/.*''',
  '''.*/mocks/.*''',
  '''e2e/.*''',
]
```

- [ ] **Step 3: Scan history + working tree.**
Run (Docker, no host install): `docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect --source=/repo --config=/repo/.gitleaks.toml --redact -v`
Expected: `no leaks found`. If a real secret is found in history, STOP and surface it to the user (rotation needed) — do not just allowlist it.

- [ ] **Step 4: Pre-commit hook.** In `lefthook.yml` `pre-commit.commands`:
```yaml
    gitleaks:
      run: docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest protect --staged --source=/repo --config=/repo/.gitleaks.toml --redact
```

- [ ] **Step 5: CI job.** In `check.yml`, add a job:
```yaml
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_CONFIG: .gitleaks.toml
```

- [ ] **Step 6: Demonstrate.** Stage a tracked file containing a synthetic AWS-style access-key assignment (prefix `AKIA` + 16 chars), run the `protect --staged` command, confirm it blocks, then unstage/delete. (Do not paste the literal key into committed docs — the repo's own semgrep hook will flag it.)

- [ ] **Step 7: Commit.**
```bash
git add .gitleaks.toml lefthook.yml .github/workflows/check.yml
git commit -m "ci: secret scanning on commit + CI (gitleaks)"
```

---

# PHASE 2 — Type checking (WS2)

## Task 5: mypy + django-stubs via baseline ratchet; fix the core

**Files:** Modify `pyproject.toml`, `Makefile`, `.github/workflows/check.yml`; Create `mypy-baseline.txt`

- [ ] **Step 1: Verify via context7** (`django-stubs`, `mypy`, `mypy-baseline`) — confirm plugin module path (`mypy_django_plugin.main`), `[tool.django-stubs]` keys, and `mypy-baseline sync`/`filter` subcommands for the installed versions.

- [ ] **Step 2: Add dev-deps.** In `[dependency-groups].dev`:
```toml
    "mypy>=1.18,<2.0",
    "django-stubs[compatible-mypy]>=5.2,<6.0",
    "djangorestframework-stubs[compatible-mypy]>=3.17,<4.0",
    "mypy-baseline>=0.7,<1.0",
```

- [ ] **Step 3: Configure mypy in `pyproject.toml`:**
```toml
[tool.mypy]
python_version = "3.13"
plugins = ["mypy_django_plugin.main", "mypy_drf_plugin.main"]
mypy_path = "backend"
namespace_packages = true
explicit_package_bases = true
ignore_missing_imports = true
check_untyped_defs = true
exclude = ['/migrations/', 'tests/']

[tool.django-stubs]
django_settings_module = "config.settings.dev"
```

- [ ] **Step 4: Generate the baseline.**
Run: `docker compose exec -w /app/backend web sh -c "uv run mypy apps config | uv run mypy-baseline sync"`
Expected: writes `backend/mypy-baseline.txt` (or repo-root per config) with current error count. Inspect the count: `wc -l backend/mypy-baseline.txt`.

- [ ] **Step 5: Confirm the gate passes against its own baseline.**
Run: `docker compose exec -w /app/backend web sh -c "uv run mypy apps config | uv run mypy-baseline filter"`
Expected: exit 0, `0 errors` after filtering.

- [ ] **Step 6: Fix the money/core modules and shrink the baseline.** For each of `apps/ai/cost.py`, `apps/ai/catalog.py`, `apps/ai/token_counter.py`, `apps/snapshots/token_budget.py`, `apps/market/returns.py`: add precise type annotations until `mypy apps/ai/cost.py` (etc.) is clean, then regenerate the baseline (Step 4) so those lines drop out. Commit annotations in small chunks. Do NOT chase unrelated errors — they stay baselined.

- [ ] **Step 7: Makefile target.**
```make
.PHONY: typecheck
typecheck: ## mypy (ORM-aware) gated against mypy-baseline.txt
	$(COMPOSE) exec -w /app/backend web sh -c "uv run mypy apps config | uv run mypy-baseline filter"
```

- [ ] **Step 8: CI step** in `check.yml` `backend` job (after ruff, a real gate — NOT continue-on-error):
```yaml
      - name: mypy (ORM-aware, baseline ratchet)
        run: cd backend && (uv run mypy apps config | uv run mypy-baseline filter)
```

- [ ] **Step 9: Demonstrate.** Introduce a clear new type error (e.g. `x: int = "s"`) in a non-baselined core file, run `make typecheck`, confirm it fails with a NEW error, revert.

- [ ] **Step 10: Commit.**
```bash
git add pyproject.toml Makefile .github/workflows/check.yml backend/mypy-baseline.txt backend/apps uv.lock
git commit -m "ci: ORM-aware mypy gate via baseline ratchet; type the cost/returns core"
```

---

# PHASE 3 — API contract (WS3)

## Task 6: drf-spectacular schema + drift gate

**Files:** Modify `pyproject.toml`, `backend/config/settings/base.py`, `backend/config/urls.py`, `Makefile`, `.github/workflows/check.yml`; Create `backend/schema.yml`

- [ ] **Step 1: Verify via context7** (`drf-spectacular`) — confirm `SPECTACULAR_SETTINGS`, `SpectacularAPIView` import path, `spectacular` management command flags.

- [ ] **Step 2: Add main-dep.** In `[project].dependencies`: `"drf-spectacular>=0.28,<1.0",`

- [ ] **Step 3: Settings.** In `base.py`, add `"drf_spectacular"` to `INSTALLED_APPS` (after `"rest_framework"`). Add to the `REST_FRAMEWORK` dict: `"DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",`. Append:
```python
SPECTACULAR_SETTINGS = {
    "TITLE": "Ledger API",
    "DESCRIPTION": "Single-user AI trading dashboard — internal API.",
    "VERSION": "0.4.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
```

- [ ] **Step 4: URL** (respect the include-ordering landmine — add as a SPECIFIC prefix BEFORE the generic `/api/` includes). In `config/urls.py`:
```python
from drf_spectacular.views import SpectacularAPIView
# ... in urlpatterns, before generic api includes:
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
```

- [ ] **Step 5: Generate the schema.**
Run: `docker compose exec -w /app/backend web uv run python manage.py spectacular --file schema.yml --validate`
Expected: writes `backend/schema.yml`; resolve any spectacular warnings (add `@extend_schema` hints on views that warn — usually a handful).

- [ ] **Step 6: Makefile + drift gate.**
```make
.PHONY: schema
schema: ## Regenerate backend/schema.yml from DRF views
	$(COMPOSE) exec -w /app/backend web uv run python manage.py spectacular --file schema.yml --validate
```
CI step in `backend` job:
```yaml
      - name: OpenAPI schema is current (drift gate)
        run: |
          cd backend && uv run python manage.py spectacular --file /tmp/schema.yml --validate
          diff -u backend/schema.yml /tmp/schema.yml
```

- [ ] **Step 7: Demonstrate.** Add a field to a serializer, run the diff step, confirm it fails (drift), regenerate + revert.

- [ ] **Step 8: Commit.**
```bash
git add pyproject.toml backend/config/settings/base.py backend/config/urls.py backend/schema.yml Makefile .github/workflows/check.yml uv.lock
git commit -m "ci: generate OpenAPI schema (drf-spectacular) + drift gate"
```

## Task 7: schemathesis fuzz lane

**Files:** Create `e2e/api/test_schemathesis.py`; Modify `pyproject.toml`, `Makefile`, `.github/workflows/e2e.yml`

- [ ] **Step 1: Verify via context7** (`schemathesis`) — confirm the current pytest integration (`schemathesis.openapi.from_url` / `schema.parametrize()`) and CLI for the installed major version.

- [ ] **Step 2: Add dev-dep.** `"schemathesis>=4.0,<5.0",`

- [ ] **Step 3: Create `e2e/api/test_schemathesis.py`** (runs under the e2e overlay where the server is live + `MOCK_EXTERNAL=true`):
```python
import os
import pytest
import schemathesis

pytestmark = pytest.mark.integration

BASE = os.environ.get("E2E_BASE_URL", "http://web:8000")
schema = schemathesis.openapi.from_url(f"{BASE}/api/schema/")

# Pre-existing contract gaps are recorded here and gated as KNOWN; new endpoints
# must pass. Empty to start; populate from Step 5 findings.
KNOWN_FAILURES: set[tuple[str, str]] = set()


@schema.parametrize()
def test_api_conforms(case):
    if (case.method, case.path) in KNOWN_FAILURES:
        pytest.xfail("known pre-existing contract gap — see plan Task 7")
    case.call_and_validate()
```

- [ ] **Step 4: Makefile target** (uses the e2e overlay machinery from the existing `e2e-*` targets):
```make
.PHONY: e2e-schemathesis
e2e-schemathesis: ## Fuzz every endpoint against the OpenAPI schema
	$(E2E_COMPOSE) up -d
	$(E2E_RUN) web uv run pytest e2e/api/test_schemathesis.py -m integration -v
```

- [ ] **Step 5: Run + triage.**
Run: `make e2e-schemathesis`
Expected: most endpoints pass. For each failure decide: real bug (fix the view/serializer) or pre-existing acceptable gap (add `(method, path)` to `KNOWN_FAILURES` with a comment). Goal: green with an explicit, reviewed `KNOWN_FAILURES` set (the ratchet — new endpoints can't silently 500).

- [ ] **Step 6: CI.** In `.github/workflows/e2e.yml`, add the schemathesis run to the api lane invocation (alongside the existing `e2e/api/` run).

- [ ] **Step 7: Commit.**
```bash
git add e2e/api/test_schemathesis.py pyproject.toml Makefile .github/workflows/e2e.yml uv.lock
git commit -m "test: fuzz the API against its OpenAPI schema (schemathesis)"
```

## Task 8: openapi-typescript generation + drift gate + incremental adoption

**Files:** Modify `frontend/package.json`, `.github/workflows/check.yml`; Create `frontend/src/api/schema.d.ts`

- [ ] **Step 1: Verify via context7** (`openapi-typescript`) — confirm the CLI invocation + output flag for the installed major version.

- [ ] **Step 2: Add devDep + script.** `pnpm add -D openapi-typescript`. In `package.json` scripts:
```json
    "gen:api": "openapi-typescript ../backend/schema.yml -o src/api/schema.d.ts"
```

- [ ] **Step 3: Generate.**
Run: `docker compose exec frontend pnpm gen:api`
Expected: writes `frontend/src/api/schema.d.ts`. `tsc --noEmit` (via `pnpm lint`) still passes.

- [ ] **Step 4: Incremental adoption (the `*_id` landmine surface).** Pick 1–2 high-churn contract types (e.g. the thread/message/snapshot response shapes) and replace their hand-written `interface` with an alias to the generated `components["schemas"][...]`, proving the generated types compile against real call sites. Do NOT convert all 481 interfaces.

- [ ] **Step 5: Drift gate.** CI step in the `frontend` job (after `pnpm install`):
```yaml
      - name: Generated API types are current (drift gate)
        run: |
          pnpm gen:api
          git diff --exit-code src/api/schema.d.ts
```

- [ ] **Step 6: Demonstrate.** Change a serializer field, regenerate `backend/schema.yml`, run `pnpm gen:api`, confirm `schema.d.ts` changes (gate would fail without regen), commit both.

- [ ] **Step 7: Commit.**
```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/src/api/schema.d.ts frontend/src .github/workflows/check.yml
git commit -m "ci: generate FE types from OpenAPI schema + drift gate (openapi-typescript)"
```

---

# PHASE 4 — Test correctness (WS4)

## Task 9: Hypothesis property tests

**Files:** Create the four `test_*_properties.py` files listed in File Structure.

> For each target: first READ the real function signature (the plan can't predict your exact API). The tests below are realistic skeletons — adapt names/imports to the actual code. Each is a property a correct implementation must satisfy.

- [ ] **Step 1: DSL evaluator** — `backend/apps/triggers/tests/test_dsl_properties.py`. Read the evaluator entry point in `apps/triggers/` first. Property: a leaf wrapped in `{"all": [leaf]}` and `{"any": [leaf]}` evaluates identically to the bare leaf; `{"not": [{"not": [x]}]}` == `x`; an empty `all` is vacuously true, empty `any` false. Use `@given` over generated metric/op/value leaves + a synthetic snapshot dict.

- [ ] **Step 2: Token budget** — `backend/apps/snapshots/tests/test_token_budget_properties.py`. Read `token_budget.py`. Property: the trimmed payload's estimated tokens never exceed the budget; trimming is idempotent (trim(trim(x)) == trim(x)); a payload already under budget is returned unchanged.

- [ ] **Step 3: Cost calc** — `backend/apps/ai/tests/test_cost_properties.py`. Read `cost.py` + `catalog.py`. Property: cost is monotonic non-decreasing in input and output tokens; zero tokens → zero cost; cost(a)+cost(b) relates correctly to cost(a+b) for the same model (linear). Use `@given` over `st.integers(min_value=0, max_value=10_000_000)`.

- [ ] **Step 4: Market hours** — `backend/apps/observer/tests/test_market_hours_properties.py`. Read `market_hours.py`. Property: `is_market_open(t)` is False for any `t` on a known weekend/holiday; for any time, open⇒within [09:30, 16:00] ET on a weekday. Use `@given` over `st.datetimes()`.

- [ ] **Step 5: Run each as you write it** (TDD discipline — the property may reveal a real edge-case bug; if so, that's a finding to fix, not a test to weaken):
Run: `docker compose exec -w /app/backend web uv run pytest apps/triggers/tests/test_dsl_properties.py apps/snapshots/tests/test_token_budget_properties.py apps/ai/tests/test_cost_properties.py apps/observer/tests/test_market_hours_properties.py -v`
Expected: PASS. If Hypothesis finds a falsifying example, decide: real bug (fix code) vs. over-broad property (tighten the property/assumptions with `assume()`).

- [ ] **Step 6: Commit.**
```bash
git add backend/apps/triggers/tests/test_dsl_properties.py backend/apps/snapshots/tests/test_token_budget_properties.py backend/apps/ai/tests/test_cost_properties.py backend/apps/observer/tests/test_market_hours_properties.py
git commit -m "test: property-based tests for DSL/token-budget/cost/market-hours (Hypothesis)"
```

## Task 10: nplusone (N+1 query gate in tests)

**Files:** Create `backend/config/settings/test.py`; Modify `pyproject.toml`, `backend/config/settings/base.py` (none needed if test settings holds it)

- [ ] **Step 1: Verify via context7** (`nplusone`) — confirm the Django integration app/middleware paths + `NPLUSONE_RAISE` setting.

- [ ] **Step 2: Add dev-dep.** `"nplusone>=1.0,<2.0",`

- [ ] **Step 3: Create `backend/config/settings/test.py`:**
```python
"""Test settings — dev plus N+1 detection that raises inside tests."""

from .dev import *  # noqa: F401,F403
from .dev import INSTALLED_APPS, MIDDLEWARE

INSTALLED_APPS = [*INSTALLED_APPS, "nplusone.ext.django"]
MIDDLEWARE = ["nplusone.ext.django.NPlusOneMiddleware", *MIDDLEWARE]
NPLUSONE_RAISE = True
```

- [ ] **Step 4: Point pytest at it.** In `pyproject.toml` `[tool.pytest.ini_options]`:
```toml
DJANGO_SETTINGS_MODULE = "config.settings.test"
```

- [ ] **Step 5: Run the suite + fix N+1s.**
Run: `docker compose exec -w /app/backend web uv run pytest -q`
Expected: `NPlusOneError` raised where a view/aggregation lazily loads in a loop (likely in `apps.analytics`, `apps.dashboard`, leaderboard). Fix each with `select_related`/`prefetch_related` until green. If a specific test legitimately can't avoid it, scope an `nplusone` ignore narrowly (documented).

- [ ] **Step 6: Commit.**
```bash
git add backend/config/settings/test.py pyproject.toml backend/apps uv.lock
git commit -m "test: detect N+1 queries in tests (nplusone) + fix offenders"
```

## Task 11: Coverage gating (backend + frontend)

**Files:** Modify `pyproject.toml`, `frontend/vite.config.ts`, `.github/workflows/check.yml`

- [ ] **Step 1: Measure current backend coverage.**
Run: `docker compose exec -w /app/backend web uv run pytest --cov=apps --cov-report=term | tail -3`
Note the TOTAL %. Set the floor to that minus a 1% buffer (e.g. measured 78% → floor 77).

- [ ] **Step 2: Backend gate.** In `pyproject.toml` add:
```toml
[tool.coverage.run]
source = ["backend/apps"]
omit = ["*/migrations/*", "*/tests/*"]

[tool.coverage.report]
fail_under = 77   # set from Step 1
```
CI already runs `--cov`; the report now fails under the floor.

- [ ] **Step 3: Measure + gate frontend.**
Run: `docker compose exec frontend pnpm run test:cov | tail -8` (note the lines/statements %). In `frontend/vite.config.ts`, under the unit project's `test.coverage`:
```ts
      coverage: {
        thresholds: { lines: 60, statements: 60, functions: 50, branches: 50 },
      },
```
(set each from the measured numbers minus a small buffer).

- [ ] **Step 4: Confirm both pass at the chosen floors.**
Run: `make test-backend` (with cov) and `make test-cov`. Expected: PASS, with a clear "coverage failure" message only if you set the floor too high.

- [ ] **Step 5: Demonstrate.** Temporarily bump the backend `fail_under` to 100, run, confirm it fails, restore.

- [ ] **Step 6: Commit.**
```bash
git add pyproject.toml frontend/vite.config.ts .github/workflows/check.yml
git commit -m "ci: gate coverage at current floor, backend + frontend"
```

## Task 12: mutmut nightly mutation report

**Files:** Modify `pyproject.toml`, `Makefile`; Create `.github/workflows/mutation.yml`

- [ ] **Step 1: Verify via context7** (`mutmut`) — confirm config key (`[tool.mutmut]` vs `setup.cfg`) and `paths_to_mutate`/`runner` syntax for the installed version.

- [ ] **Step 2: Add dev-dep.** `"mutmut>=3.2,<4.0",`

- [ ] **Step 3: Configure** (`pyproject.toml`), scoped to the money paths only:
```toml
[tool.mutmut]
paths_to_mutate = "backend/apps/ai/cost.py,backend/apps/ai/catalog.py,backend/apps/thesis/services/postmortem.py,backend/apps/market/returns.py"
runner = "uv run pytest -x -q apps/ai/tests apps/thesis/tests apps/market/tests"
```

- [ ] **Step 4: Makefile target.**
```make
.PHONY: mutate
mutate: ## Mutation-test the money paths (slow; nightly in CI)
	$(COMPOSE) exec -w /app/backend web uv run mutmut run || true
	$(COMPOSE) exec -w /app/backend web uv run mutmut results
```

- [ ] **Step 5: Smoke-run locally** on one file to confirm config works (`mutmut run` then `mutmut results`); survivors indicate weak assertions — note them but do NOT block on fixing all now.

- [ ] **Step 6: Nightly workflow `.github/workflows/mutation.yml`** (mirror `flake-audit.yml`'s shape: `schedule` cron + `workflow_dispatch`, bring stack up, run `make mutate`, upload results artifact). Not a PR gate.

- [ ] **Step 7: Commit.**
```bash
git add pyproject.toml Makefile .github/workflows/mutation.yml uv.lock
git commit -m "ci: nightly mutation testing on the money paths (mutmut)"
```

---

# PHASE 5 — Error visibility (WS5)

## Task 13: Sentry (off by default via env)

**Files:** Modify `pyproject.toml`, `backend/config/settings/base.py`, `.env.example`

- [ ] **Step 1: Verify via context7** (`sentry-sdk`) — confirm `sentry_sdk.init` + `DjangoIntegration`/`CeleryIntegration` import paths for the installed version.

- [ ] **Step 2: Add main-dep.** `"sentry-sdk[django,celery]>=2.20,<3.0",`

- [ ] **Step 3: Init block** appended to `base.py` (env-gated — empty DSN is a complete no-op):
```python
# Error visibility (opt-in): only initializes when SENTRY_DSN is set. Surfaces the
# warn-and-continue / _safe() swallow points so silent degradation is visible.
SENTRY_DSN = env.str("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
        environment=env.str("SENTRY_ENVIRONMENT", default="dev"),
    )
```

- [ ] **Step 4: Capture the swallow points.** In the highest-value `_safe`/except-and-continue sites (`apps/dashboard` rollup `_safe`, `apps/briefing/services/assemble.py`, `apps/coverage/services/revise.py`, `apps/thesis/services/postmortem.py` narrative), add inside the `except` (guarded so it's a no-op without Sentry):
```python
import sentry_sdk
sentry_sdk.capture_exception()  # no-op if SENTRY_DSN unset
```

- [ ] **Step 5: Document env.** In `.env.example` add:
```
# Optional error tracking — leave blank to disable (no-op). Set to a Sentry DSN to enable.
SENTRY_DSN=
```

- [ ] **Step 6: Verify no-op + lock.**
Run: `uv lock && docker compose exec web uv sync --frozen` then `make test-backend` (subset). Expected: PASS with `SENTRY_DSN` unset — nothing initializes, nothing transmitted.

- [ ] **Step 7: Commit.**
```bash
git add pyproject.toml backend/config/settings/base.py backend/apps .env.example uv.lock
git commit -m "feat(infra): opt-in Sentry error tracking (no-op until SENTRY_DSN set)"
```

---

# PHASE 6 — Docs + final verification

## Task 14: CLAUDE.md + full green

**Files:** Modify `CLAUDE.md`

- [ ] **Step 1: Daily-commands table** — add rows for `make check-migrations`, `make lint-imports`, `make typecheck`, `make schema`, `make e2e-schemathesis`, `make mutate`.

- [ ] **Step 2: Testing / landmines sections** — note the new gates: import contracts enforce the documented cycles; mypy is now an ORM-aware baseline-ratchet gate (ty stays advisory/local); the OpenAPI schema + generated FE types are drift-gated (reinforces the `*_id` contract); coverage is floor-gated; nplusone runs via `config.settings.test`; gitleaks on commit; Sentry opt-in.

- [ ] **Step 3: Run the conventions-check skill** on the diff (the repo provides it) to confirm no landmine was tripped by these changes.

- [ ] **Step 4: Full local gate.**
Run: `make check`
Expected: lint (ruff + ty advisory + import-linter + eslint/tsc) and all tests green.

- [ ] **Step 5: E2E sanity** (the lanes touched by schema/schemathesis):
Run: `make e2e-api && make e2e-schemathesis`
Expected: PASS.

- [ ] **Step 6: Commit + open PR.**
```bash
git add CLAUDE.md
git commit -m "docs: record new quality gates in CLAUDE.md"
git push -u origin chore/quality-tooling
gh pr create --title "Quality & correctness tooling (13 hard-gated checks)" --body "Implements docs/superpowers/specs/2026-06-03-quality-tooling-design.md"
```

---

## Self-Review (completed by author)

- **Spec coverage:** all 13 tools mapped — import-linter (T3), mypy+django-stubs (T5), drf-spectacular (T6), schemathesis (T7), openapi-typescript (T8), Hypothesis (T9), nplusone (T10), coverage (T11), mutmut (T12), gitleaks (T4), pytest-randomly+timeout (T1), makemigrations-check (T2), Sentry (T13). Ratchets (mypy baseline, schemathesis KNOWN_FAILURES, FE incremental adoption) and docs (T14) covered.
- **Placeholders:** coverage floors (`77`, `60`) and import-linter `source_modules` are explicitly resolved by a measurement/discovery step within their task — not TODOs.
- **Type consistency:** Makefile target names (`check-migrations`, `lint-imports`, `typecheck`, `schema`, `gen:api`/`gen-api`, `mutate`, `e2e-schemathesis`) are used consistently across tasks, CI, and the docs task.
- **Ordering:** schemathesis (T7) and openapi-typescript (T8) correctly follow drf-spectacular (T6, produces `schema.yml`). nplusone (T10) creates the `config.settings.test` module that pytest then uses; coverage (T11) runs after so its measurement reflects the final settings.
