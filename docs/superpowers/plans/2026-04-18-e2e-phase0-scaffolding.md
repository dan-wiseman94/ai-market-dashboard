# E2E Phase 0 — Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the foundation for the six-lane comprehensive E2E suite — new directory tree, Make targets, GHA workflow skeleton, relocated existing journeys, and the ~25 frontend testids needed by later phases.

**Architecture:** Non-behavior-changing scaffolding. Move 6 existing journeys from `e2e/journeys/` into `e2e/ui/`. Add empty conftest shells for each lane. Add `data-testid` to select DOM nodes. No new assertions yet.

**Tech Stack:** pytest, pytest-xdist, pytest-timeout, pytest-playwright, Django, React+Vite.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §2 (architecture), §6 (POM/testids), §9 (execution/CI), §10 Phase 0.

---

## File structure

**Create:**
- `e2e/ui/` — Playwright journeys (6 moved + empty subdirs)
- `e2e/api/`, `e2e/ws/`, `e2e/visual/`, `e2e/a11y/`, `e2e/perf/` — lane dirs with `__init__.py` + `conftest.py` stubs
- `e2e/mocks/__init__.py`, `e2e/mocks/client.py` — empty placeholders
- `e2e/helpers/__init__.py` — placeholder; real helpers land in later phases
- `e2e/README.md` — short pointer doc
- `.github/workflows/e2e.yml` — six-job skeleton
- `pytest.ini` sections (already present) — add `timeout` via `addopts` per lane (done in later phases; this phase only wires markers)

**Modify:**
- `Makefile` — add 11 new targets
- `frontend/src/components/NotificationBell.tsx` — confirm testid present (already has one)
- `frontend/src/components/layout/AppLayout.tsx` — add testids
- `frontend/src/components/layout/TopNav.tsx` — add testids
- `frontend/src/components/layout/Breadcrumbs.tsx` — add testid
- `frontend/src/components/layout/CommandPalette.tsx` — add testid
- `frontend/src/components/Skeleton.tsx` — update pattern to `data-testid="skeleton-<where>"`
- `frontend/src/components/Toasts.tsx` — testid per toast
- `frontend/src/components/BranchTabs.tsx` — `branch-cost-<n>` (already partially present)
- `frontend/src/components/costs/DailyCostChart.tsx` — `cost-tile-today`
- `frontend/src/pages/DashboardPage.tsx` (if exists — find real file) — card testids
- `frontend/src/pages/SnapshotComposerPage.tsx` — `capture-btn`, `send-ai-btn`
- `frontend/src/pages/ThreadDetailPage.tsx` — `message-<id>`, `compose-input`
- `frontend/src/pages/SchedulesPage.tsx` — `schedule-row-<id>`
- `frontend/src/pages/TriggersListPage.tsx` — `trigger-row-<id>`
- `frontend/src/pages/AnalyticsPage.tsx` — `analytics-card-<kind>`
- `frontend/src/pages/WatchlistsList.tsx` — `watchlist-row-<name>`
- `frontend/src/pages/ProfilesPage.tsx` — `profile-row-<name>`
- `frontend/src/pages/BackupsPage.tsx` — `backup-row-<id>`
- `frontend/src/pages/ExportPage.tsx` — `export-row-<id>`
- `frontend/src/pages/SnapshotComposerPage.tsx` — `section-<name>-status`
- `frontend/src/components/FilesList.tsx` (or wherever files render) — `file-row-<id>`
- `frontend/src/components/Citation.tsx` — `citation-<id>`
- `frontend/src/components/ConnectionStatusDot.tsx` — `connection-status-dot`

**Move:**
- `e2e/journeys/test_capture_to_cost.py` → `e2e/ui/test_snapshots_capture_gold.py`
- `e2e/journeys/test_compare_flow.py` → `e2e/ui/test_compare_two_branches_gold.py`
- `e2e/journeys/test_observer_to_thread.py` → `e2e/ui/test_observer_run_now_gold.py`
- `e2e/journeys/test_trigger_firing.py` → `e2e/ui/test_trigger_fire_gold.py`
- `e2e/journeys/test_backup_roundtrip.py` → `e2e/ui/test_backups_gold.py`
- `e2e/journeys/test_export_roundtrip.py` → `e2e/ui/test_export_gold.py`
- Delete `e2e/journeys/` after move.

**Delete:**
- `e2e/journeys/` (after move)
- Existing page-object stubs — keep them for now; Phase 2 replaces them.

---

## Task 1 — Create new lane directory skeleton

**Files:**
- Create: `e2e/ui/__init__.py`, `e2e/ui/conftest.py`
- Create: `e2e/api/__init__.py`, `e2e/api/conftest.py`
- Create: `e2e/ws/__init__.py`, `e2e/ws/conftest.py`
- Create: `e2e/visual/__init__.py`, `e2e/visual/conftest.py`, `e2e/visual/__screenshots__/.gitkeep`
- Create: `e2e/a11y/__init__.py`, `e2e/a11y/conftest.py`
- Create: `e2e/perf/__init__.py`, `e2e/perf/conftest.py`, `e2e/perf/budgets.json`
- Create: `e2e/mocks/__init__.py`, `e2e/mocks/client.py`
- Create: `e2e/helpers/__init__.py`

- [ ] **Step 1: Write collection test**

Create `e2e/tests/test_scaffolding.py`:

```python
"""Scaffolding collection test — asserts new lane dirs are importable."""
from __future__ import annotations


def test_lane_packages_importable() -> None:
    import e2e.ui  # noqa: F401
    import e2e.api  # noqa: F401
    import e2e.ws  # noqa: F401
    import e2e.visual  # noqa: F401
    import e2e.a11y  # noqa: F401
    import e2e.perf  # noqa: F401
    import e2e.mocks  # noqa: F401
    import e2e.helpers  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest e2e/tests/test_scaffolding.py::test_lane_packages_importable -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'e2e.ui'` (or similar for first missing module).

- [ ] **Step 3: Create empty `__init__.py` for every new lane/package**

```bash
for d in ui api ws visual a11y perf mocks helpers; do
  mkdir -p e2e/$d
  : > e2e/$d/__init__.py
done
mkdir -p e2e/visual/__screenshots__
: > e2e/visual/__screenshots__/.gitkeep
```

- [ ] **Step 4: Create per-lane conftest placeholders**

Each lane conftest is a no-op until later phases populate it. Create `e2e/ui/conftest.py`:

```python
"""UI lane conftest — Playwright fixtures are inherited from top-level e2e/conftest.py."""
from __future__ import annotations
```

Create `e2e/api/conftest.py`:

```python
"""API lane conftest — httpx client fixtures land here in Phase 2."""
from __future__ import annotations
```

Create `e2e/ws/conftest.py`:

```python
"""WS lane conftest — websockets client fixtures land here in Phase 5."""
from __future__ import annotations
```

Create `e2e/visual/conftest.py`:

```python
"""Visual lane conftest — stability + masking helpers land here in Phase 6."""
from __future__ import annotations
```

Create `e2e/a11y/conftest.py`:

```python
"""A11y lane conftest — axe runner fixtures land here in Phase 7."""
from __future__ import annotations
```

Create `e2e/perf/conftest.py`:

```python
"""Perf lane conftest — Lighthouse runner fixtures land here in Phase 7."""
from __future__ import annotations
```

Create `e2e/perf/budgets.json`:

```json
{
  "/": {"LCP": 2500, "CLS": 0.10, "TBT": 300, "performance": 0.85},
  "/snapshot": {"LCP": 2500, "CLS": 0.10, "TBT": 400, "performance": 0.80},
  "/threads/:id": {"LCP": 3000, "CLS": 0.10, "TBT": 400, "performance": 0.80},
  "/costs": {"LCP": 2500, "CLS": 0.10, "TBT": 300, "performance": 0.85},
  "/analytics": {"LCP": 3500, "CLS": 0.10, "TBT": 500, "performance": 0.75}
}
```

Create `e2e/mocks/client.py`:

```python
"""ScenarioClient — Phase 1 implements the header-injection logic.

This placeholder keeps imports valid during Phase 0.
"""
from __future__ import annotations
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec web pytest e2e/tests/test_scaffolding.py::test_lane_packages_importable -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add e2e/ui e2e/api e2e/ws e2e/visual e2e/a11y e2e/perf e2e/mocks e2e/helpers e2e/tests/test_scaffolding.py
git commit -m "$(cat <<'EOF'
chore(e2e): create six-lane directory skeleton

Empty __init__.py and conftest placeholders for ui/api/ws/visual/a11y/perf.
Scaffolding for mocks and helpers packages. budgets.json with Phase 7 targets.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — Move existing journeys into `e2e/ui/`

**Files:**
- Move: 6 files from `e2e/journeys/` to `e2e/ui/`
- Delete: `e2e/journeys/` directory

- [ ] **Step 1: Move and rename journey files**

```bash
git mv e2e/journeys/test_capture_to_cost.py       e2e/ui/test_snapshots_capture_gold.py
git mv e2e/journeys/test_compare_flow.py          e2e/ui/test_compare_two_branches_gold.py
git mv e2e/journeys/test_observer_to_thread.py    e2e/ui/test_observer_run_now_gold.py
git mv e2e/journeys/test_trigger_firing.py        e2e/ui/test_trigger_fire_gold.py
git mv e2e/journeys/test_backup_roundtrip.py      e2e/ui/test_backups_gold.py
git mv e2e/journeys/test_export_roundtrip.py      e2e/ui/test_export_gold.py
git rm e2e/journeys/__init__.py
rmdir e2e/journeys
```

- [ ] **Step 2: Update imports inside moved files**

None of the moved files import from `e2e.journeys.*`, so no in-file changes are required. Grep to confirm:

```bash
grep -rn "e2e.journeys" e2e/ backend/ || echo "clean"
```

Expected: `clean`.

- [ ] **Step 3: Collection test that the moved tests still import**

Add to `e2e/tests/test_scaffolding.py`:

```python
def test_ui_journeys_importable() -> None:
    import importlib
    for mod in [
        "e2e.ui.test_snapshots_capture_gold",
        "e2e.ui.test_compare_two_branches_gold",
        "e2e.ui.test_observer_run_now_gold",
        "e2e.ui.test_trigger_fire_gold",
        "e2e.ui.test_backups_gold",
        "e2e.ui.test_export_gold",
    ]:
        importlib.import_module(mod)
```

- [ ] **Step 4: Run collection test**

Run: `docker compose exec web pytest e2e/tests/test_scaffolding.py::test_ui_journeys_importable -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(e2e): move journeys into e2e/ui lane

6 existing Playwright journeys moved from e2e/journeys/ to e2e/ui/ and
renamed to the <feature>_<scenario>_gold pattern. e2e/journeys/ removed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — Expand top-level `e2e/conftest.py`

**Files:**
- Modify: `e2e/conftest.py`

- [ ] **Step 1: Write failing test for new fixtures**

Add to `e2e/tests/test_scaffolding.py`:

```python
import pytest


@pytest.mark.integration
def test_api_base_url_fixture(api_base_url: str) -> None:
    assert api_base_url.startswith("http://")


@pytest.mark.integration
def test_frontend_base_url_fixture(frontend_base_url: str) -> None:
    assert frontend_base_url.startswith("http://")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest e2e/tests/test_scaffolding.py::test_api_base_url_fixture -v`
Expected: FAIL — `fixture 'api_base_url' not found`.

- [ ] **Step 3: Add URL fixtures to `e2e/conftest.py`**

Append to `e2e/conftest.py`:

```python
@pytest.fixture(scope="session")
def api_base_url() -> str:
    return E2E_BASE_URL


@pytest.fixture(scope="session")
def frontend_base_url() -> str:
    return E2E_FRONTEND_URL
```

- [ ] **Step 4: Register extra pytest markers**

Inside `pytest_configure(config)` in `e2e/conftest.py`, append:

```python
    config.addinivalue_line("markers", "ui: UI lane browser tests")
    config.addinivalue_line("markers", "api: API lane httpx contract tests")
    config.addinivalue_line("markers", "ws: WebSocket lane tests")
    config.addinivalue_line("markers", "visual: visual regression tests")
    config.addinivalue_line("markers", "a11y: accessibility scan tests")
    config.addinivalue_line("markers", "perf: performance budget tests")
```

- [ ] **Step 5: Run tests to verify fixtures work**

Run: `docker compose exec web pytest e2e/tests/test_scaffolding.py -v`
Expected: 3 tests PASS (lane packages + journeys + api_base_url + frontend_base_url).

- [ ] **Step 6: Commit**

```bash
git add e2e/conftest.py e2e/tests/test_scaffolding.py
git commit -m "$(cat <<'EOF'
feat(e2e): add url fixtures + lane markers to conftest

api_base_url, frontend_base_url session fixtures.
pytest markers: ui, api, ws, visual, a11y, perf.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — Add Make targets for all six lanes

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Write failing test for new targets**

Create `e2e/tests/test_makefile.py`:

```python
"""Make target surface tests."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _makefile_text() -> str:
    return Path("/app/Makefile").read_text() if Path("/app/Makefile").exists() else Path("Makefile").read_text()


def test_makefile_has_lane_targets() -> None:
    text = _makefile_text()
    for target in (
        "e2e-ui:", "e2e-api:", "e2e-ws:", "e2e-visual:",
        "e2e-visual-update:", "e2e-a11y:", "e2e-perf:",
        "e2e-up:", "e2e-down:",
    ):
        assert target in text, f"missing Make target: {target}"


def test_makefile_help_includes_lane_targets() -> None:
    """Lane targets must have help comments so `make help` lists them."""
    text = _makefile_text()
    for line in ("e2e-ui:", "e2e-api:", "e2e-ws:", "e2e-visual:", "e2e-a11y:", "e2e-perf:"):
        assert f"{line}" in text
        # each target should be followed on the same line by a ## comment
        for row in text.splitlines():
            if row.startswith(line):
                assert "## " in row, f"{line} missing `## description`"
                break
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest e2e/tests/test_makefile.py -v`
Expected: FAIL on `e2e-ui:`.

- [ ] **Step 3: Append lane targets to `Makefile`**

Append to `Makefile`:

```makefile
.PHONY: e2e-up
e2e-up: ## Bring e2e stack up with overlay, leave running
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d

.PHONY: e2e-down
e2e-down: ## Tear down e2e stack
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml down

.PHONY: e2e-ui
e2e-ui: ## E2E UI lane (Playwright journeys)
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/ui/ -n 4 --dist=loadscope -v

.PHONY: e2e-api
e2e-api: ## E2E API lane (httpx contract)
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/api/ -n 4 -v

.PHONY: e2e-ws
e2e-ws: ## E2E WebSocket lane
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/ws/ -n 2 -v

.PHONY: e2e-visual
e2e-visual: ## E2E visual regression lane
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/visual/ -n 2 -v

.PHONY: e2e-visual-update
e2e-visual-update: ## Regenerate visual baselines
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/visual/ --update-snapshots -v
	@echo "Inspect diffs: git diff e2e/visual/__screenshots__/"

.PHONY: e2e-a11y
e2e-a11y: ## E2E accessibility lane
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/a11y/ -n 4 -v

.PHONY: e2e-perf
e2e-perf: ## E2E performance lane (runs prod overlay)
	$(COMPOSE) -f compose.yaml -f compose.prod.yaml up -d
	$(COMPOSE) exec web pytest e2e/perf/ -v
```

- [ ] **Step 4: Update existing `e2e` target to run all lanes**

Replace the existing `e2e:` recipe with:

```makefile
.PHONY: e2e
e2e: ## Run all E2E lanes sequentially
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml up -d
	$(COMPOSE) exec web pytest e2e/ui/ e2e/api/ e2e/ws/ e2e/visual/ e2e/a11y/ -n 4 --dist=loadscope -v
	$(COMPOSE) -f compose.yaml -f compose.e2e.yaml down
```

(Perf is excluded from `make e2e` because it requires the prod overlay; run it explicitly.)

- [ ] **Step 5: Run test to verify targets exist**

Run: `docker compose exec web pytest e2e/tests/test_makefile.py -v`
Expected: PASS.

- [ ] **Step 6: Verify `make help` lists them**

Run: `make help | grep e2e-`
Expected: All 9 e2e-* targets listed with descriptions.

- [ ] **Step 7: Commit**

```bash
git add Makefile e2e/tests/test_makefile.py
git commit -m "$(cat <<'EOF'
feat(build): add per-lane E2E Make targets

e2e-ui/api/ws/visual/a11y/perf lane targets plus e2e-up/down/visual-update
helpers. Updated `make e2e` to run all lanes with xdist parallelism.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — GitHub Actions workflow skeleton

**Files:**
- Create: `.github/workflows/e2e.yml`

- [ ] **Step 1: Write workflow validation test**

Create `e2e/tests/test_gha_workflow.py`:

```python
"""GHA workflow sanity checks."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_e2e_workflow_has_six_lane_jobs() -> None:
    wf_path = Path("/app/.github/workflows/e2e.yml") if Path("/app/.github/workflows/e2e.yml").exists() \
              else Path(".github/workflows/e2e.yml")
    wf = yaml.safe_load(wf_path.read_text())
    jobs = wf["jobs"]
    for lane in ("e2e-ui", "e2e-api", "e2e-ws", "e2e-visual", "e2e-a11y", "e2e-perf"):
        assert lane in jobs, f"missing GHA job: {lane}"


def test_e2e_workflow_has_summary_job() -> None:
    wf_path = Path("/app/.github/workflows/e2e.yml") if Path("/app/.github/workflows/e2e.yml").exists() \
              else Path(".github/workflows/e2e.yml")
    wf = yaml.safe_load(wf_path.read_text())
    assert "e2e-summary" in wf["jobs"]
    summary = wf["jobs"]["e2e-summary"]
    assert "if" in summary and "always()" in summary["if"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest e2e/tests/test_gha_workflow.py -v`
Expected: FAIL — file not found or missing jobs.

- [ ] **Step 3: Create `.github/workflows/e2e.yml`**

```yaml
name: e2e

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-images:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - name: Build images
        run: docker compose -f compose.yaml -f compose.e2e.yaml build
      - name: Save images to artifact
        run: |
          docker save $(docker compose -f compose.yaml -f compose.e2e.yaml config --images) -o /tmp/images.tar
      - uses: actions/upload-artifact@v4
        with:
          name: docker-images
          path: /tmp/images.tar
          retention-days: 1

  e2e-ui:
    needs: build-images
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: docker-images
          path: /tmp
      - run: docker load -i /tmp/images.tar
      - run: docker compose -f compose.yaml -f compose.e2e.yaml up -d
      - run: docker compose exec -T web pytest e2e/ui/ -n 4 --dist=loadscope -v --tracing=retain-on-failure
      - if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: ui-traces
          path: e2e/artifacts/

  e2e-api:
    needs: build-images
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {name: docker-images, path: /tmp}
      - run: docker load -i /tmp/images.tar
      - run: docker compose -f compose.yaml -f compose.e2e.yaml up -d
      - run: docker compose exec -T web pytest e2e/api/ -n 4 -v

  e2e-ws:
    needs: build-images
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {name: docker-images, path: /tmp}
      - run: docker load -i /tmp/images.tar
      - run: docker compose -f compose.yaml -f compose.e2e.yaml up -d
      - run: docker compose exec -T web pytest e2e/ws/ -n 2 -v

  e2e-visual:
    needs: build-images
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {name: docker-images, path: /tmp}
      - run: docker load -i /tmp/images.tar
      - run: docker compose -f compose.yaml -f compose.e2e.yaml up -d
      - run: docker compose exec -T web pytest e2e/visual/ -n 2 -v
      - if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: visual-diffs
          path: e2e/visual/test-results/

  e2e-a11y:
    needs: build-images
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {name: docker-images, path: /tmp}
      - run: docker load -i /tmp/images.tar
      - run: docker compose -f compose.yaml -f compose.e2e.yaml up -d
      - run: docker compose exec -T web pytest e2e/a11y/ -n 4 -v
      - if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: a11y-violations
          path: e2e/a11y/artifacts/

  e2e-perf:
    needs: build-images
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {name: docker-images, path: /tmp}
      - run: docker load -i /tmp/images.tar
      - run: docker compose -f compose.yaml -f compose.prod.yaml up -d
      - run: docker compose exec -T web pytest e2e/perf/ -v
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: lighthouse-reports
          path: e2e/perf/artifacts/

  e2e-summary:
    needs: [e2e-ui, e2e-api, e2e-ws, e2e-visual, e2e-a11y, e2e-perf]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Write lane matrix summary
        run: |
          cat <<EOF > $GITHUB_STEP_SUMMARY
          | Lane | Status |
          |------|--------|
          | ui | ${{ needs.e2e-ui.result }} |
          | api | ${{ needs.e2e-api.result }} |
          | ws | ${{ needs.e2e-ws.result }} |
          | visual | ${{ needs.e2e-visual.result }} |
          | a11y | ${{ needs.e2e-a11y.result }} |
          | perf | ${{ needs.e2e-perf.result }} |
          EOF
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest e2e/tests/test_gha_workflow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/e2e.yml e2e/tests/test_gha_workflow.py
git commit -m "$(cat <<'EOF'
ci(e2e): six-lane GHA workflow skeleton

Jobs: build-images, e2e-ui/api/ws/visual/a11y/perf, e2e-summary.
Uses docker image artifact reuse across lanes (~4 min saved per lane).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — Add 25 frontend testids (pt 1 — layout + shared components)

**Files:**
- Modify: `frontend/src/components/layout/TopNav.tsx`, `Breadcrumbs.tsx`, `CommandPalette.tsx`, `ConnectionStatusDot.tsx`, `NotificationBell.tsx`, `Skeleton.tsx`, `Toasts.tsx`

- [ ] **Step 1: Write vitest snapshot for testid presence**

Create `frontend/src/__tests__/testids/layout.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import TopNav from "../../components/layout/TopNav";
import Breadcrumbs from "../../components/layout/Breadcrumbs";
import ConnectionStatusDot from "../../components/ConnectionStatusDot";
import NotificationBell from "../../components/NotificationBell";

describe("layout testids", () => {
  it("TopNav exposes breadcrumb-trail + notification-bell + connection-status-dot", () => {
    render(
      <MemoryRouter>
        <TopNav />
      </MemoryRouter>
    );
    expect(screen.getByTestId("breadcrumb-trail")).toBeInTheDocument();
    expect(screen.getByTestId("notification-bell")).toBeInTheDocument();
    expect(screen.getByTestId("connection-status-dot")).toBeInTheDocument();
  });

  it("Breadcrumbs root has data-testid='breadcrumb-trail'", () => {
    render(<MemoryRouter><Breadcrumbs /></MemoryRouter>);
    expect(screen.getByTestId("breadcrumb-trail")).toBeInTheDocument();
  });

  it("ConnectionStatusDot has data-testid='connection-status-dot'", () => {
    render(<ConnectionStatusDot />);
    expect(screen.getByTestId("connection-status-dot")).toBeInTheDocument();
  });

  it("NotificationBell has data-testid='notification-bell'", () => {
    render(<NotificationBell />);
    expect(screen.getByTestId("notification-bell")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npm test -- --run src/__tests__/testids/layout.test.tsx`
Expected: FAIL — some testids missing.

- [ ] **Step 3: Add missing testids**

For each file that's missing the testid, add it to the outermost render root. Example for `frontend/src/components/layout/Breadcrumbs.tsx` — find the outer `<nav>` or `<ol>` and add `data-testid="breadcrumb-trail"`:

```tsx
<nav aria-label="Breadcrumb" data-testid="breadcrumb-trail">
  {/* ... */}
</nav>
```

For `frontend/src/components/ConnectionStatusDot.tsx`, add to the outer `<span>`:

```tsx
<span data-testid="connection-status-dot" className={`dot ${statusClass}`} aria-label={label} />
```

For `frontend/src/components/NotificationBell.tsx`, confirm testid — spec grep already shows one. Keep it.

For `frontend/src/components/Skeleton.tsx`, change to pattern:

```tsx
<div data-testid={`skeleton-${where ?? "generic"}`} className="skeleton" aria-busy="true" />
```

(Add `where?: string` prop.)

For `frontend/src/components/Toasts.tsx`, each toast wrapper:

```tsx
<div data-testid={`toast-${kind}`} role="status" className={`toast toast-${kind}`}>
  {/* ... */}
</div>
```

For `frontend/src/components/layout/CommandPalette.tsx`, outer `<div>`:

```tsx
<div data-testid="command-palette" role="dialog" aria-modal="true">
  {/* ... */}
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend npm test -- --run src/__tests__/testids/layout.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ frontend/src/__tests__/testids/
git commit -m "$(cat <<'EOF'
feat(frontend): testids on shared layout components

breadcrumb-trail, notification-bell, connection-status-dot, command-palette,
toast-<kind>, skeleton-<where>. Enables reliable E2E selectors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 — Add 25 frontend testids (pt 2 — page-level row/card ids)

**Files:**
- Modify: `frontend/src/pages/SchedulesPage.tsx`, `TriggersListPage.tsx`, `AnalyticsPage.tsx`, `WatchlistsList.tsx`, `ProfilesPage.tsx`, `BackupsPage.tsx`, `ExportPage.tsx`, `ThreadsPage.tsx`, `ThreadDetailPage.tsx`, `SnapshotComposerPage.tsx`, `Dashboard.tsx`
- Modify: `frontend/src/components/BranchTabs.tsx`, `costs/DailyCostChart.tsx`, `FilesList.tsx` (if present), `Citation.tsx`

- [ ] **Step 1: Write vitest for page-level testids (one combined test per row kind)**

Create `frontend/src/__tests__/testids/rows.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";

// These tests render each page with a minimal mock hook so we can verify
// that rendering a list correctly tags rows. We keep mocks ultra-minimal —
// just enough to hit the testid code path.

describe("page testids — rows + cards", () => {
  it("SchedulesPage row carries data-testid='schedule-row-<id>'", async () => {
    const { default: SchedulesPage } = await import("../../pages/SchedulesPage");
    // Mock useSchedules hook to return one row
    vi.doMock("../../hooks/useSchedules", () => ({
      default: () => ({ data: [{ id: 42, name: "t", interval_seconds: 60 }], isLoading: false }),
    }));
    render(<MemoryRouter><SchedulesPage /></MemoryRouter>);
    expect(screen.getByTestId("schedule-row-42")).toBeInTheDocument();
  });

  it("TriggersListPage row carries data-testid='trigger-row-<id>'", async () => {
    const { default: Page } = await import("../../pages/TriggersListPage");
    vi.doMock("../../hooks/useTriggers", () => ({
      default: () => ({ data: [{ id: 7, name: "t" }], isLoading: false }),
    }));
    render(<MemoryRouter><Page /></MemoryRouter>);
    expect(screen.getByTestId("trigger-row-7")).toBeInTheDocument();
  });

  it("AnalyticsPage exposes analytics-card-<kind> for each card", async () => {
    const { default: Page } = await import("../../pages/AnalyticsPage");
    render(<MemoryRouter><Page /></MemoryRouter>);
    for (const kind of ["leaderboard", "cpi", "heatmap", "timeline", "unusual-options"]) {
      expect(screen.getByTestId(`analytics-card-${kind}`)).toBeInTheDocument();
    }
  });
});
```

- [ ] **Step 2: Run to verify failures**

Run: `docker compose exec frontend npm test -- --run src/__tests__/testids/rows.test.tsx`
Expected: FAIL on first missing testid.

- [ ] **Step 3: Add testids**

In each list page's row-render map, add `data-testid={...}`. Example for `SchedulesPage.tsx`:

```tsx
{schedules.map((s) => (
  <tr key={s.id} data-testid={`schedule-row-${s.id}`}>
    {/* existing cells */}
  </tr>
))}
```

Similar for `TriggersListPage`, `WatchlistsList` (`watchlist-row-${w.name}`), `ProfilesPage` (`profile-row-${p.name}`), `BackupsPage` (`backup-row-${b.id}`), `ExportPage` (`export-row-${e.id}`), `ThreadsPage` (`thread-row-${t.id}`).

For `AnalyticsPage`, wrap each card:

```tsx
<section data-testid="analytics-card-leaderboard" className="card">
  <LeaderboardCard />
</section>
<section data-testid="analytics-card-cpi" className="card">
  <CostPerInsightCard />
</section>
<section data-testid="analytics-card-heatmap" className="card">
  <TriggerHeatmapCard />
</section>
<section data-testid="analytics-card-timeline" className="card">
  <ObserverTimelineCard />
</section>
<section data-testid="analytics-card-unusual-options" className="card">
  <UnusualOptionsCard />
</section>
```

For `ThreadDetailPage.tsx`, add:

```tsx
<textarea data-testid="compose-input" {...} />
<ul role="log">
  {messages.map((m) => (
    <li key={m.id} data-testid={`message-${m.id}`}>...</li>
  ))}
</ul>
```

For `SnapshotComposerPage.tsx`:

```tsx
<button data-testid="capture-btn" onClick={handleCapture}>Capture</button>
<button data-testid="send-ai-btn" onClick={handleSend}>Send to AI</button>
<!-- per section status -->
{sections.map((s) => (
  <div key={s.name} data-testid={`section-${s.name}-status`}>{s.status}</div>
))}
```

For `frontend/src/components/costs/DailyCostChart.tsx`, wrap the outer:

```tsx
<div data-testid="cost-tile-today">
  {/* chart */}
</div>
```

For `BranchTabs.tsx`, per-branch cost tile:

```tsx
<div data-testid={`branch-cost-${n}`}>${cost.toFixed(4)}</div>
```

For `Citation.tsx`:

```tsx
<a data-testid={`citation-${id}`} href={url}>...</a>
```

For any file-row list component (`FilesList.tsx` or wherever `UserFile` rows render):

```tsx
<li key={f.id} data-testid={`file-row-${f.id}`}>...</li>
```

- [ ] **Step 4: Run tests to verify pass**

Run: `docker compose exec frontend npm test -- --run src/__tests__/testids/`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
feat(frontend): page-level testids for lists + cards

schedule-row, trigger-row, thread-row, watchlist-row, profile-row,
backup-row, export-row, file-row, message-<id>, citation-<id>,
analytics-card-<kind>, cost-tile-today, branch-cost-<n>, compose-input,
capture-btn, send-ai-btn, section-<name>-status.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 — Short e2e/README.md pointer doc

**Files:**
- Create: `e2e/README.md`

- [ ] **Step 1: Write README contents**

Create `e2e/README.md`:

```markdown
# E2E test suite

Six-lane comprehensive suite. Full design: `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md`.

## Lane layout

| Lane     | Dir               | What it tests                               | Run locally          |
|----------|-------------------|---------------------------------------------|----------------------|
| UI       | `e2e/ui/`         | Playwright browser journeys                 | `make e2e-ui`        |
| API      | `e2e/api/`        | httpx contract against DRF endpoints        | `make e2e-api`       |
| WS       | `e2e/ws/`         | Channels WebSocket event assertions         | `make e2e-ws`        |
| Visual   | `e2e/visual/`     | Page-level screenshot diffs                 | `make e2e-visual`    |
| A11y     | `e2e/a11y/`       | axe-core scans per route + keyboard-only    | `make e2e-a11y`      |
| Perf     | `e2e/perf/`       | Lighthouse budgets (prod overlay)           | `make e2e-perf`      |

`make e2e` runs ui/api/ws/visual/a11y together. Perf is separate because it
needs the prod overlay.

## Workflow

```
# First time
make e2e-up                              # build + start stack with overlay

# Iterate
make e2e-one t=ui/test_snapshots_capture_gold.py
HEADED=1 make e2e-one t=ui/test_snapshots_capture_gold.py   # visual debug

# Update visual baselines
make e2e-visual-update
git diff e2e/visual/__screenshots__/

# Tear down
make e2e-down
```

## Troubleshooting

- **"Mocked response" in a non-mock test** — you've got the e2e overlay still
  up. Stop it: `make e2e-down`.
- **Visual baseline missing** — first-run creates it. Commit the new PNGs.
- **Perf test fails on LCP** — check `e2e/perf/artifacts/` for the Lighthouse
  HTML report; budgets live in `e2e/perf/budgets.json`.
- **Flaky UI test** — don't add `@pytest.mark.flaky` without a linked issue.
  See `tools/flake_audit.py` (Phase 8).
```

- [ ] **Step 2: Commit**

```bash
git add e2e/README.md
git commit -m "$(cat <<'EOF'
docs(e2e): short README pointing at spec + lane runbook

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 0 acceptance

- [ ] `docker compose exec web pytest e2e/tests/ -v` — all scaffolding tests pass.
- [ ] `make help` lists all 9 new `e2e-*` targets.
- [ ] `docker compose exec frontend npm test -- --run src/__tests__/testids/` — all pass.
- [ ] `make e2e-ui` still runs the 6 relocated journeys successfully (MOCK_EXTERNAL=true).
- [ ] `.github/workflows/e2e.yml` validates (`yamllint .github/workflows/e2e.yml` or run the workflow on a test branch).
- [ ] `e2e/journeys/` no longer exists.
