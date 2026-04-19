# E2E Phase 8 — Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the assembled suite into something that stays green — nightly flake audit, PR-comment artifact aggregator, console/network guards, and a runbook.

**Architecture:** `tools/flake_audit.py` re-runs every lane 3× and logs per-test pass/fail to `flake_audit.json`. A GHA cron weekly opens an issue with the top-10 flakiest tests. The `e2e-summary` job is upgraded from a bare `$GITHUB_STEP_SUMMARY` dump to a single consolidated PR comment. Every UI test automatically fails on unexpected `console.error` or 5xx network responses via a conftest hook.

**Tech Stack:** Python stdlib + `github-script` action (already in GHA ecosystem).

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §8 (flake + failure strategy), §10 Phase 8.

**Prerequisite:** Phases 0–7 complete and stable on main for ≥1 week before relying on flake_audit data.

---

## File structure

**Create:**
- `tools/flake_audit.py`
- `tools/aggregate_artifacts.py`
- `.github/workflows/flake-audit.yml`
- `e2e/helpers/console_guard.py`

**Modify:**
- `e2e/ui/conftest.py` — wire console_guard into every UI test
- `e2e/README.md` — runbook sections

---

## Task 1 — Console + network guard

**Files:**
- Create: `e2e/helpers/console_guard.py`
- Modify: `e2e/ui/conftest.py`

- [ ] **Step 1: Test**

Create `e2e/tests/test_console_guard.py`:

```python
"""Guard interface test."""
from __future__ import annotations


def test_console_guard_api() -> None:
    from e2e.helpers import console_guard
    assert hasattr(console_guard, "attach")
    assert hasattr(console_guard, "ALLOWED_CONSOLE_PATTERNS")
    assert hasattr(console_guard, "ALLOWED_NETWORK_PATHS")
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

```python
"""Attach to a Playwright page so any console.error or unexpected 5xx fails the test.

Usage (conftest.py):
    @pytest.fixture(autouse=True)
    def _guard_ui(page, request):
        if not request.node.get_closest_marker("ui"):
            yield
            return
        errors = console_guard.attach(page)
        yield
        if errors:
            pytest.fail("Unexpected console/network errors:\\n" + "\\n".join(errors))
"""
from __future__ import annotations

import re
from playwright.sync_api import Page


ALLOWED_CONSOLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"/render/chart"),  # known benign warning from chart render route
    re.compile(r"React DevTools"),
]


ALLOWED_NETWORK_PATHS: list[re.Pattern] = [
    re.compile(r"/ws/"),  # websocket upgrades sometimes report as errors in devtools
]


def attach(page: Page) -> list[str]:
    errors: list[str] = []

    def _on_console(msg):
        if msg.type != "error":
            return
        text = msg.text
        if any(p.search(text) for p in ALLOWED_CONSOLE_PATTERNS):
            return
        errors.append(f"CONSOLE: {text}")

    def _on_pageerror(err):
        errors.append(f"PAGEERROR: {err}")

    def _on_response(resp):
        if resp.status >= 500 and not any(p.search(resp.url) for p in ALLOWED_NETWORK_PATHS):
            errors.append(f"NETWORK {resp.status}: {resp.url}")

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)
    page.on("response", _on_response)
    return errors
```

- [ ] **Step 4: Wire into UI conftest**

Extend `e2e/ui/conftest.py`:

```python
"""UI lane conftest — playwright fixtures inherited; console guard is autouse."""
from __future__ import annotations

import pytest

from e2e.helpers import console_guard


@pytest.fixture(autouse=True)
def _console_guard(page, request):
    marker = request.node.get_closest_marker("ui")
    if marker is None:
        yield
        return
    errors = console_guard.attach(page)
    yield
    if errors:
        pytest.fail("Unexpected console/network errors:\n" + "\n".join(errors))
```

- [ ] **Step 5: Smoke test against existing UI**

Run: `docker compose exec web pytest e2e/ui/test_dashboard.py -v`

If a previously-green test now fails because of a benign console log, either fix the log source or add a new entry to `ALLOWED_CONSOLE_PATTERNS` with a rationale comment.

- [ ] **Step 6: Commit**

```bash
git add e2e/helpers/console_guard.py e2e/ui/conftest.py e2e/tests/test_console_guard.py
git commit -m "$(cat <<'EOF'
feat(e2e/ui): console + network guard auto-fails UI tests

Catches silent JS errors and unexpected 5xx responses that tests would
otherwise miss. Allowlist lives in console_guard.py with comments.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — `flake_audit.py`

**Files:**
- Create: `tools/flake_audit.py`

- [ ] **Step 1: Implement**

```python
#!/usr/bin/env python3
"""Re-runs every e2e lane 3× and logs per-test pass/fail ratios.

Reads the JUnit XML outputs from each run, computes flake rates, and writes
flake_audit.json. Designed to run in GitHub Actions cron (see flake-audit.yml).
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

RUNS = 3
LANES = ["ui", "api", "ws"]  # visual/a11y/perf excluded — they're handled separately
ARTIFACTS = Path("flake_audit_runs")


def run_lane(lane: str, run_idx: int) -> Path:
    out = ARTIFACTS / f"{lane}-run-{run_idx}.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exec inside the web container
    subprocess.run(
        [
            "docker", "compose", "exec", "-T", "web",
            "pytest", f"e2e/{lane}/",
            "-n", "4", f"--junit-xml={out}",
        ],
        check=False,
    )
    return out


def parse_junit(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}
    tree = ET.parse(path)
    results: dict[str, bool] = {}
    for case in tree.iter("testcase"):
        name = f"{case.get('classname')}::{case.get('name')}"
        failed = any(c.tag in ("failure", "error") for c in case)
        results[name] = not failed
    return results


def main() -> int:
    stats: dict[str, list[bool]] = defaultdict(list)
    for lane in LANES:
        for i in range(RUNS):
            out = run_lane(lane, i)
            for name, passed in parse_junit(out).items():
                stats[name].append(passed)

    flaky = []
    for name, runs in stats.items():
        if 0 < sum(runs) < len(runs):  # any mix of pass/fail
            flaky.append({
                "test": name,
                "passes": sum(runs),
                "runs": len(runs),
                "flake_rate": round(1 - sum(runs) / len(runs), 3),
            })

    flaky.sort(key=lambda x: x["flake_rate"], reverse=True)
    Path("flake_audit.json").write_text(json.dumps({
        "total_tests": len(stats),
        "flaky_count": len(flaky),
        "flaky": flaky[:20],
    }, indent=2))

    print(f"Total tests: {len(stats)} | Flaky: {len(flaky)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Test import + no-op run**

```bash
chmod +x tools/flake_audit.py
docker compose exec web python tools/flake_audit.py || echo "ok (may run lanes)"
```

- [ ] **Step 3: Commit**

```bash
git add tools/flake_audit.py
git commit -m "feat(tools): flake_audit.py — 3x lane re-runs + flake_audit.json

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — Nightly flake-audit GHA workflow

**Files:**
- Create: `.github/workflows/flake-audit.yml`

- [ ] **Step 1: Workflow**

```yaml
name: flake-audit

on:
  schedule:
    - cron: '0 6 * * *'   # daily 06:00 UTC (02:00 ET)
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
      - name: Bring up stack
        run: docker compose -f compose.yaml -f compose.e2e.yaml up -d --build
      - name: Run flake audit
        run: docker compose exec -T web python tools/flake_audit.py
      - uses: actions/upload-artifact@v4
        with:
          name: flake_audit
          path: |
            flake_audit.json
            flake_audit_runs/

  weekly-issue:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' && github.event.schedule == '0 6 * * 1'  # Mondays
    needs: audit
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: {name: flake_audit, path: .}
      - uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const data = JSON.parse(fs.readFileSync('flake_audit.json', 'utf8'));
            if (data.flaky_count === 0) return;
            const body = [
              `## Weekly flake audit — ${new Date().toISOString().slice(0, 10)}`,
              ``,
              `Total tests: ${data.total_tests} | Flaky: ${data.flaky_count}`,
              ``,
              `### Top flaky tests`,
              ``,
              `| Test | flake rate | passes/runs |`,
              `|------|-----------:|------------:|`,
              ...data.flaky.slice(0, 10).map(t =>
                `| \`${t.test}\` | ${(t.flake_rate*100).toFixed(1)}% | ${t.passes}/${t.runs} |`),
            ].join('\n');
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `E2E flake audit — ${new Date().toISOString().slice(0, 10)}`,
              body,
              labels: ['e2e', 'flake'],
            });
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/flake-audit.yml
git commit -m "ci(e2e): nightly flake audit + weekly issue automation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 — Artifact aggregator → PR comment

**Files:**
- Create: `tools/aggregate_artifacts.py`
- Modify: `.github/workflows/e2e.yml` — replace `e2e-summary` body

- [ ] **Step 1: Aggregator**

```python
#!/usr/bin/env python3
"""Consume per-lane artifacts and emit a single PR-comment-ready markdown blob."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def build_summary() -> str:
    lines = [
        "## E2E results",
        "",
        "| Lane | Result | Tests | Artifacts |",
        "|------|--------|------:|-----------|",
    ]
    for lane in ("ui", "api", "ws", "visual", "a11y", "perf"):
        result_file = Path(f"artifacts/{lane}-result.json")
        if not result_file.exists():
            lines.append(f"| {lane} | ⚠ missing | — | — |")
            continue
        data = json.loads(result_file.read_text())
        icon = "✅" if data["passed"] else "❌"
        artifact_links = " / ".join(f"[{n}]({u})" for n, u in data.get("artifacts", {}).items()) or "—"
        lines.append(f"| {lane} | {icon} | {data.get('tests', '—')} | {artifact_links} |")

    # A11y breakdown
    a11y_dir = Path("artifacts/a11y-violations")
    if a11y_dir.exists():
        lines += ["", "### A11y violations"]
        for f in sorted(a11y_dir.glob("*.json")):
            v = json.loads(f.read_text())
            lines.append(f"- `{f.stem}`: {len(v)} violations")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_summary())
```

- [ ] **Step 2: Wire into e2e.yml**

Replace the `e2e-summary` job in `.github/workflows/e2e.yml`:

```yaml
  e2e-summary:
    needs: [e2e-ui, e2e-api, e2e-ws, e2e-visual, e2e-a11y, e2e-perf]
    if: always()
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          path: artifacts
      - id: aggregate
        run: |
          summary=$(python tools/aggregate_artifacts.py)
          {
            echo "summary<<EOF"
            echo "$summary"
            echo "EOF"
          } >> "$GITHUB_OUTPUT"
      - name: Post PR comment
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const body = `${{ steps.aggregate.outputs.summary }}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body,
            });
      - name: Write step summary
        run: echo "${{ steps.aggregate.outputs.summary }}" >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 3: Commit**

```bash
git add tools/aggregate_artifacts.py .github/workflows/e2e.yml
git commit -m "$(cat <<'EOF'
feat(ci): consolidated E2E PR comment + step-summary aggregator

Single comment per PR with per-lane pass/fail, test count, artifact links,
and a11y breakdown. Replaces the bare step-summary dump.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Extend `e2e/README.md` to a full runbook

**Files:**
- Modify: `e2e/README.md`

- [ ] **Step 1: Extend README**

Append sections:

```markdown

## Troubleshooting matrix

| Symptom                                      | Likely cause                                          | Fix                                                       |
|----------------------------------------------|-------------------------------------------------------|-----------------------------------------------------------|
| `ui` test fails with "CONSOLE" error         | JS error in the frontend                              | Fix it. Add to ALLOWED_CONSOLE_PATTERNS only if benign.   |
| `visual` test fails with masked region      | New dynamic region rendered outside mask              | Add it to `default_masks()` in `helpers/visual.py`.       |
| `a11y` axe violation on new page             | Missing aria-label / heading / focus style            | Fix the DOM. Do not add to a11y_ignores without issue link.|
| `perf` LCP over budget                       | Blocking JS / large image on critical path            | Check artifact lighthouse-reports/<route>/median.html.    |
| `ws` test hangs                              | Backend not producing the event or wrong scenario     | Inspect `docker compose logs web worker`.                 |
| "Mocked response" appears in prod test       | e2e overlay left running                              | `make e2e-down`.                                          |
| New test failing only in CI                  | Likely timing/flake                                   | Check `flake_audit.json` on latest main.                  |

## When to open an issue vs. fix in-flight

- Single flaky-looking failure on a never-flaky test: rerun once, then open issue if it recurs.
- Baseline drift after unrelated change: investigate; don't blindly update baselines.
- New a11y violation introduced by your branch: fix it in your branch.
- Lighthouse regression > 10% on a route: block the PR; do not bump the budget without rationale.

## Adding a new feature

1. Add a UI gold test to the appropriate `e2e/ui/test_<feature>.py`.
2. Add an API contract test to `e2e/api/test_<feature>_contract.py`.
3. If the feature introduces a WS event, add a `e2e/ws/test_<feature>.py` test.
4. Capture a visual baseline: `make e2e-visual-update`.
5. Run `make e2e-a11y` to confirm no new violations.
6. If the route is new + non-trivial, add it to `e2e/perf/budgets.json` + `test_lighthouse.py`.

## Scenario engine cheat sheet

```python
def test_something(page, frontend_base_url, minimal, scenario):
    scenario.use("claude-5xx-midstream")
    # ... test code ...
```

Available scenarios: see `backend/apps/core/mocks/scenarios.py`. Add new scenarios
by inserting an entry there + a handler function in `providers.py`.
```

- [ ] **Step 2: Commit**

```bash
git add e2e/README.md
git commit -m "docs(e2e): runbook — troubleshooting matrix + new-feature steps

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 8 acceptance

- [ ] UI lane autofails on unexpected console/pageerror/5xx.
- [ ] `tools/flake_audit.py` runs against the stack and emits `flake_audit.json`.
- [ ] `.github/workflows/flake-audit.yml` scheduled; manual dispatch works.
- [ ] Weekly issue automation fires on Monday 06:00 UTC.
- [ ] PR comments show the consolidated lane matrix + artifact links.
- [ ] `e2e/README.md` contains the troubleshooting matrix + new-feature checklist.
- [ ] Full `make e2e` on a fresh clone completes within 30 min.
- [ ] CI `e2e` workflow green on main for 14 consecutive days.
