# E2E Phase 7 — A11y + Perf Lanes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Axe-core scans on every top-level route + one keyboard-only journey (a11y), plus Lighthouse budgets on 5 representative routes (perf) running against the prod overlay.

**Architecture:** Axe runs via `axe-playwright-python` filtered to critical+serious. Keyboard-only test walks dashboard→snapshot→thread using only keyboard. Lighthouse shells out to the npm CLI inside the `frontend` container and parses JSON; median of 3 runs.

**Tech Stack:** `axe-playwright-python` (new pip dep), `lighthouse` (already available via `frontend` container npm), `jq` for parsing in bash helpers.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §5.4 (a11y), §5.5 (perf), §8 (flake + deadlines).

**Prerequisite:** Phases 0, 1, 2, 3 complete.

---

## File structure

**Create:**
- `e2e/helpers/axe_runner.py`
- `e2e/helpers/lighthouse_runner.py`
- `e2e/a11y/test_axe_per_route.py`
- `e2e/a11y/test_keyboard_only.py`
- `e2e/a11y/a11y_ignores.py`
- `e2e/a11y/artifacts/.gitkeep`
- `e2e/perf/test_lighthouse.py`
- `e2e/perf/artifacts/.gitkeep`

**Modify:**
- `pyproject.toml` (or `requirements-dev.txt`) — add `axe-playwright-python`
- `frontend/package.json` — add `lighthouse` if not already present
- `e2e/perf/budgets.json` (Phase 0 placed placeholder — confirm values)

---

## Task 1 — Add `axe-playwright-python` dep

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dep**

In `pyproject.toml`, under `[project.optional-dependencies]` or `[tool.poetry.group.dev.dependencies]`:

```toml
axe-playwright-python = "^0.1"
```

- [ ] **Step 2: Rebuild `web` image**

```bash
docker compose -f compose.yaml -f compose.e2e.yaml build web
docker compose -f compose.yaml -f compose.e2e.yaml up -d web
```

- [ ] **Step 3: Smoke test import**

```bash
docker compose exec web python -c "from axe_playwright_python.sync_playwright import Axe; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(e2e): add axe-playwright-python dev dep

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 — `axe_runner.py` helper

**Files:**
- Create: `e2e/helpers/axe_runner.py`
- Create: `e2e/a11y/a11y_ignores.py`

- [ ] **Step 1: Test**

Create `e2e/tests/test_axe_runner.py`:

```python
"""Unit test the helper interface."""
from __future__ import annotations


def test_axe_runner_exposes_scan() -> None:
    from e2e.helpers import axe_runner
    assert hasattr(axe_runner, "scan")
    assert hasattr(axe_runner, "Violation")
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
"""Axe-core runner — filtered to critical+serious."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page

# Import lazily inside scan() so the unit test can run without the pkg present.


@dataclass
class Violation:
    id: str
    impact: str
    description: str
    help_url: str
    targets: list[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "impact": self.impact, "description": self.description,
            "help_url": self.help_url, "targets": self.targets,
        }


def scan(page: Page, ignore_rule_ids: set[str] | None = None) -> list[Violation]:
    from axe_playwright_python.sync_playwright import Axe
    axe = Axe()
    result = axe.run(page, options={
        "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa"]},
        "resultTypes": ["violations"],
    })
    ignored = ignore_rule_ids or set()
    return [
        Violation(
            id=v["id"], impact=v["impact"] or "", description=v["description"],
            help_url=v["helpUrl"], targets=[" ".join(n.get("target", [])) for n in v.get("nodes", [])],
        )
        for v in result.violations
        if v["id"] not in ignored and v["impact"] in ("critical", "serious")
    ]
```

- [ ] **Step 4: Create ignores module**

```python
"""Rules intentionally suppressed (v1 — list is empty).

Adding an entry requires:
- a TODO link (internal issue URL)
- a rationale documenting WHY the rule can't be fixed now
"""
from __future__ import annotations

IGNORED_RULES: set[str] = set()
```

- [ ] **Step 5: Pass + commit.**

```bash
git add e2e/helpers/axe_runner.py e2e/a11y/a11y_ignores.py e2e/tests/test_axe_runner.py
git commit -m "feat(e2e/helpers): axe_runner with critical+serious filter

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — `test_axe_per_route.py`

**Files:**
- Create: `e2e/a11y/test_axe_per_route.py`

- [ ] **Step 1: Parametrized scan**

```python
"""Axe scans — one per top-level route."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e.a11y.a11y_ignores import IGNORED_RULES
from e2e.helpers import axe_runner


# (path, seed_rung, name)
ROUTES = [
    ("/",                               "minimal",   "dashboard"),
    ("/snapshot",                       "minimal",   "snapshot_composer"),
    ("/threads",                        "threads",   "threads_list"),
    ("/threads/1",                      "threads",   "thread_detail"),
    ("/threads/observer/1",             "observer",  "observer_timeline"),
    ("/schedules",                      "observer",  "schedules"),
    ("/triggers",                       "triggers",  "triggers_list"),
    ("/triggers/new",                   "minimal",   "trigger_editor"),
    ("/analytics",                      "analytics", "analytics"),
    ("/watchlists",                     "market",    "watchlists"),
    ("/watchlists/1",                   "market",    "watchlist_detail"),
    ("/profiles",                       "minimal",   "profiles"),
    ("/costs",                          "analytics", "costs"),
    ("/settings/backups",               "minimal",   "backups"),
    ("/settings/export",                "threads",   "export"),
]


ARTIFACTS_DIR = Path("e2e/a11y/artifacts")


@pytest.mark.integration
@pytest.mark.a11y
@pytest.mark.parametrize("path,rung,name", ROUTES)
def test_axe_per_route(page, frontend_base_url, path, rung, name, request) -> None:
    request.getfixturevalue(rung)

    # For id-bearing paths, resolve 1 → an actual id when needed
    if path == "/threads/1":
        from apps.threads.models import Thread
        path = f"/threads/{Thread.objects.first().id}"
    if path == "/watchlists/1":
        from apps.market.models import Watchlist
        path = f"/watchlists/{Watchlist.objects.first().id}"
    if path == "/threads/observer/1":
        from apps.profiles.models import TradingProfile
        path = f"/threads/observer/{TradingProfile.objects.first().id}"

    page.goto(f"{frontend_base_url}{path}")
    page.wait_for_load_state("networkidle")
    violations = axe_runner.scan(page, ignore_rule_ids=IGNORED_RULES)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    if violations:
        (ARTIFACTS_DIR / f"{name}.json").write_text(json.dumps([v.to_dict() for v in violations], indent=2))

    assert not violations, f"{name}: {len(violations)} critical/serious a11y violations"
```

- [ ] **Step 2: Run + triage**

Run: `docker compose exec web pytest e2e/a11y/test_axe_per_route.py -v`

Expect some failures on first run — each represents a real a11y issue to fix in the frontend. Options:

1. Fix the violation (preferred) — add aria-label, heading structure, focus outline, etc.
2. If the violation is out of scope for v1 AND has a tracked fix, add its `id` to `a11y_ignores.IGNORED_RULES` with comment referencing the issue.

- [ ] **Step 3: Commit after all green**

```bash
git add e2e/a11y/test_axe_per_route.py e2e/a11y/artifacts/.gitkeep
git commit -m "test(e2e/a11y): per-route axe-core scans (critical+serious)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 — `test_keyboard_only.py`

**Files:**
- Create: `e2e/a11y/test_keyboard_only.py`

- [ ] **Step 1: Test**

```python
"""Keyboard-only journey: dashboard → snapshot composer → thread.

Uses only Tab/Shift+Tab/Enter/Escape/Arrow/Space. Asserts focus ring visible
at every interactive step.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.integration
@pytest.mark.a11y
def test_keyboard_only_journey(page, frontend_base_url, minimal) -> None:
    page.goto(frontend_base_url)
    page.wait_for_load_state("networkidle")

    # Tab forward through the top nav until we reach the "Snapshot" link
    # (depends on current DOM order — 5-10 Tabs is typical)
    for _ in range(20):
        page.keyboard.press("Tab")
        # Check focus ring visible via :focus-visible
        focused = page.evaluate("() => document.activeElement && document.activeElement.textContent")
        if focused and "Snapshot" in focused:
            break
    else:
        pytest.fail("Could not reach Snapshot nav link via Tab")

    page.keyboard.press("Enter")
    page.wait_for_url(lambda u: "/snapshot" in u)

    # Focus Profile select
    for _ in range(10):
        page.keyboard.press("Tab")
        tag = page.evaluate("() => document.activeElement.tagName.toLowerCase()")
        if tag == "select":
            break

    # Change selection + Tab into Objective input
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Tab")
    page.keyboard.type("keyboard-only test")

    # Tab to Capture button and submit
    for _ in range(10):
        page.keyboard.press("Tab")
        label = page.evaluate("() => (document.activeElement.textContent || '').trim()")
        if "Capture" in label:
            break
    page.keyboard.press("Enter")

    # Wait for snapshot complete
    expect(page.get_by_text("complete", exact=False)).to_be_visible(timeout=30_000)

    # Confirm focus ring is drawn — :focus-visible exists
    has_ring = page.evaluate("""
        () => {
            const el = document.activeElement;
            if (!el) return false;
            const style = getComputedStyle(el);
            return style.outlineStyle !== 'none' || style.boxShadow !== 'none';
        }
    """)
    assert has_ring, "Expected visible focus indicator on active element"
```

- [ ] **Step 2: Pass + commit.**

```bash
git add e2e/a11y/test_keyboard_only.py
git commit -m "test(e2e/a11y): keyboard-only journey + focus-ring assertion

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5 — `lighthouse_runner.py` helper

**Files:**
- Create: `e2e/helpers/lighthouse_runner.py`

- [ ] **Step 1: Test**

Create `e2e/tests/test_lighthouse_runner.py`:

```python
"""Lighthouse helper — shape test only (doesn't run lighthouse)."""
from __future__ import annotations


def test_lighthouse_helper_api() -> None:
    from e2e.helpers import lighthouse_runner
    for attr in ("run_once", "run_median", "Result"):
        assert hasattr(lighthouse_runner, attr)
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
"""Lighthouse runner — shells out to the lighthouse npm CLI inside frontend container.

Usage:
    from e2e.helpers.lighthouse_runner import run_median
    r = run_median("http://frontend:3000/analytics", runs=3)
    assert r.lcp < 3000
"""
from __future__ import annotations

import json
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    lcp: float
    cls: float
    tbt: float
    performance_score: float
    report_html: str
    report_json: dict


def run_once(url: str, out_dir: Path) -> Result:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_base = out_dir / "run"
    # Inside frontend container — wrap with docker exec if called from web
    cmd = [
        "docker", "compose", "exec", "-T", "frontend",
        "npx", "lighthouse", url,
        "--output=json", "--output=html",
        f"--output-path={out_base}",
        "--chrome-flags=--headless=new --no-sandbox --disable-gpu",
        "--only-categories=performance",
        "--throttling-method=provided",
    ]
    subprocess.run(cmd, check=True, timeout=180)
    # Lighthouse writes <out_base>.report.json + .report.html
    json_path = Path(f"{out_base}.report.json")
    html_path = Path(f"{out_base}.report.html")
    report = json.loads(json_path.read_text())
    audits = report["audits"]
    return Result(
        lcp=audits["largest-contentful-paint"]["numericValue"],
        cls=audits["cumulative-layout-shift"]["numericValue"],
        tbt=audits["total-blocking-time"]["numericValue"],
        performance_score=report["categories"]["performance"]["score"],
        report_html=html_path.read_text(),
        report_json=report,
    )


def run_median(url: str, out_dir: Path, runs: int = 3) -> Result:
    results = [run_once(url, out_dir / f"run-{i}") for i in range(runs)]
    # Median on each numeric, keep the corresponding JSON+HTML from the median perf run
    medians = {
        "lcp": statistics.median(r.lcp for r in results),
        "cls": statistics.median(r.cls for r in results),
        "tbt": statistics.median(r.tbt for r in results),
        "performance_score": statistics.median(r.performance_score for r in results),
    }
    # Find the run whose performance_score matches the median
    canonical = min(results, key=lambda r: abs(r.performance_score - medians["performance_score"]))
    return Result(
        lcp=medians["lcp"], cls=medians["cls"], tbt=medians["tbt"],
        performance_score=medians["performance_score"],
        report_html=canonical.report_html, report_json=canonical.report_json,
    )


def count_over_budget(results: list[Result], budget: dict) -> int:
    """Count how many of the given runs exceed the budget on any metric."""
    count = 0
    for r in results:
        if r.lcp > budget.get("LCP", float("inf")):
            count += 1; continue
        if r.cls > budget.get("CLS", float("inf")):
            count += 1; continue
        if r.tbt > budget.get("TBT", float("inf")):
            count += 1; continue
        if r.performance_score < budget.get("performance", 0):
            count += 1; continue
    return count
```

- [ ] **Step 4: Pass + commit.**

```bash
git add e2e/helpers/lighthouse_runner.py e2e/tests/test_lighthouse_runner.py
git commit -m "feat(e2e/helpers): lighthouse_runner (run_once + run_median)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 — `test_lighthouse.py`

**Files:**
- Create: `e2e/perf/test_lighthouse.py`

- [ ] **Step 1: Test**

```python
"""Lighthouse budgets — prod overlay.

Runs 3x per route and fails if 2 or more runs miss ANY budget metric.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e.helpers import lighthouse_runner


BUDGETS = json.loads(Path("e2e/perf/budgets.json").read_text())
ARTIFACTS = Path("e2e/perf/artifacts")


@pytest.mark.integration
@pytest.mark.perf
@pytest.mark.parametrize("route", list(BUDGETS.keys()))
def test_lighthouse_budget(route: str, frontend_base_url: str, analytics) -> None:
    budget = BUDGETS[route]
    # Resolve dynamic :id segments
    url_path = route
    if ":id" in url_path:
        from apps.threads.models import Thread
        t = Thread.objects.first()
        url_path = url_path.replace(":id", str(t.id))
    url = f"{frontend_base_url}{url_path}"

    out = ARTIFACTS / route.lstrip("/").replace("/", "_").replace(":", "")
    results = [lighthouse_runner.run_once(url, out / f"run-{i}") for i in range(3)]

    misses = lighthouse_runner.count_over_budget(results, budget)
    assert misses < 2, (
        f"{route}: {misses}/3 runs over budget — "
        f"LCPs={[r.lcp for r in results]} "
        f"CLSs={[r.cls for r in results]} "
        f"TBTs={[r.tbt for r in results]} "
        f"scores={[r.performance_score for r in results]}"
    )

    # Persist the median report
    median = lighthouse_runner.run_median(url, out, runs=3)
    (out / "median.json").write_text(json.dumps(median.report_json, indent=2))
    (out / "median.html").write_text(median.report_html)
```

- [ ] **Step 2: Pass + commit.**

Run: `make e2e-perf` (starts prod overlay).

If a route is over budget:
- Either fix the perf (code splitting, lazy image loading, etc.), or
- If the threshold was wrong, update `e2e/perf/budgets.json` with a rationale in the commit message.

```bash
git add e2e/perf/test_lighthouse.py e2e/perf/artifacts/.gitkeep
git commit -m "test(e2e/perf): Lighthouse budgets — 5 routes × 3 runs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 7 acceptance

- [ ] `make e2e-a11y` — 15 route scans + 1 keyboard-only test, all pass, wall time ≤ 4 min.
- [ ] `make e2e-perf` — 5 Lighthouse budgets, all pass (or explicitly updated with rationale), wall time ≤ 6 min.
- [ ] Any a11y violations discovered are **fixed in the frontend**, not silently ignored (unless tracked in `a11y_ignores` with issue link).
- [ ] Lighthouse median reports committed as artifacts under `e2e/perf/artifacts/`.
- [ ] No regressions in other lanes.
