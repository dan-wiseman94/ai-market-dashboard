# E2E Phase 6 — Visual Regression Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Page-level screenshot diffs for every top-level route — 20 baselines, deterministic chromium renders inside the `web` container.

**Architecture:** One parametrized test per route. `helpers/visual.py` provides `wait_for_stable()`, animation/font/pointer disablers, and the default mask set. Baselines live in `e2e/visual/__screenshots__/<test>/linux/<name>.png`, committed to git. Pre-commit hook enforces ≤500KB per baseline.

**Tech Stack:** Playwright's built-in `to_have_screenshot()` (via `pytest-playwright`); no external tooling.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §5.3, §7.

**Prerequisite:** Phases 0, 1, 2, 3 complete (gold UI tests surface the routes we'll snapshot).

---

## File structure

**Create:**
- `e2e/helpers/visual.py`
- `e2e/visual/test_route_snapshots.py`
- `e2e/visual/__screenshots__/.gitattributes`
- `.git/hooks/pre-commit` (or `tools/hooks/pre-commit-visual.sh` invoked via `.pre-commit-config.yaml`)

**Modify:**
- `.gitattributes` (repo root) — mark `e2e/visual/__screenshots__/**/*.png` as binary
- `e2e/visual/conftest.py` — add viewport + color-scheme fixture overrides

---

## Task 1 — `helpers/visual.py`

**Files:**
- Create: `e2e/helpers/visual.py`

- [ ] **Step 1: Test**

Create `e2e/tests/test_visual_helpers.py`:

```python
"""Unit test for helper shape."""
from __future__ import annotations


def test_visual_helper_api() -> None:
    from e2e.helpers import visual
    assert hasattr(visual, "wait_for_stable")
    assert hasattr(visual, "default_masks")
    assert hasattr(visual, "disable_animations")
    assert hasattr(visual, "suppress_pointer_effects")
```

- [ ] **Step 2: Fail** — module missing.

- [ ] **Step 3: Implement**

```python
"""Visual regression helpers — stability waits + masking."""
from __future__ import annotations

from playwright.sync_api import Locator, Page


def disable_animations(page: Page) -> None:
    page.add_style_tag(content=(
        "*, *::before, *::after { "
        "animation: none !important; "
        "animation-duration: 0s !important; "
        "transition: none !important; "
        "transition-duration: 0s !important; "
        "}"
    ))


def suppress_pointer_effects(page: Page) -> None:
    """Freezes charts + interactive overlays during capture."""
    page.add_style_tag(content=(
        "canvas, svg, [data-chart] { pointer-events: none !important; } "
        "[data-hover], [data-hover='true'] { opacity: 0 !important; }"
    ))


def wait_for_stable(page: Page, timeout_ms: int = 5000) -> None:
    page.wait_for_load_state("networkidle")
    page.evaluate("() => document.fonts.ready")
    try:
        page.wait_for_selector("[data-testid^='skeleton-']", state="detached", timeout=timeout_ms)
    except Exception:  # noqa: BLE001
        pass
    disable_animations(page)
    suppress_pointer_effects(page)


def default_masks(page: Page) -> list[Locator]:
    """The default masks applied to every page-level screenshot."""
    return [
        page.get_by_test_id("cost-tile-today"),
        page.get_by_test_id("notification-bell"),
        page.locator(".timestamp"),
        page.locator("[data-chart] canvas"),
        page.get_by_test_id("breadcrumb-trail"),
    ]
```

- [ ] **Step 4: Pass.**

Run: `docker compose exec web pytest e2e/tests/test_visual_helpers.py -v`

- [ ] **Step 5: Commit**

```bash
git add e2e/helpers/visual.py e2e/tests/test_visual_helpers.py
git commit -m "feat(e2e/helpers): visual stability helpers

wait_for_stable disables animations, hides pointer effects, waits for
fonts + skeleton teardown. default_masks returns the shared mask set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 — Visual conftest: viewport + color-scheme

**Files:**
- Modify: `e2e/visual/conftest.py`

- [ ] **Step 1: Implement**

```python
"""Visual lane conftest — pin viewport + color scheme."""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, BrowserContext


@pytest.fixture
def context(browser: Browser):
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        device_scale_factor=1,
        color_scheme="light",
    )
    yield ctx
    ctx.close()
```

- [ ] **Step 2: Commit**

```bash
git add e2e/visual/conftest.py
git commit -m "chore(e2e/visual): pin viewport 1280x800 light scheme

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — `.gitattributes` + screenshot dir setup

**Files:**
- Modify: `.gitattributes`
- Create: `e2e/visual/__screenshots__/.gitattributes`

- [ ] **Step 1: Root `.gitattributes` append**

```
e2e/visual/__screenshots__/**/*.png binary
```

- [ ] **Step 2: Commit**

```bash
git add .gitattributes
git commit -m "chore: mark visual baselines as binary for diff tooling

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 — `test_route_snapshots.py`

**Files:**
- Create: `e2e/visual/test_route_snapshots.py`

- [ ] **Step 1: Parametrized route snapshot test**

```python
"""Page-level screenshots for every top-level route.

Baselines land in e2e/visual/__screenshots__/<test>/linux/<name>.png.
Update: make e2e-visual-update.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from e2e.helpers.visual import default_masks, wait_for_stable


# (path, seed_rung, snapshot_name)
ROUTES = [
    ("/",                                   "analytics", "dashboard"),
    ("/settings",                           "minimal",   "settings_general"),
    ("/settings/backups",                   "minimal",   "settings_backups"),
    ("/settings/export",                    "threads",   "settings_export"),
    ("/watchlists",                         "market",    "watchlists_list"),
    ("/market/AAPL",                        "market",    "market_ticker"),
    ("/profiles",                           "minimal",   "profiles"),
    ("/snapshot",                           "minimal",   "snapshot_composer_empty"),
    ("/threads",                            "threads",   "threads_list"),
    ("/costs",                              "analytics", "costs_today"),
    ("/schedules",                          "observer",  "schedules"),
    ("/triggers",                           "triggers",  "triggers_list"),
    ("/triggers/new",                       "minimal",   "trigger_editor"),
    ("/analytics",                          "analytics", "analytics"),
]


@pytest.mark.integration
@pytest.mark.visual
@pytest.mark.parametrize("path,rung,name", ROUTES)
def test_route_snapshot(page: Page, frontend_base_url: str, path: str, rung: str, name: str, request) -> None:
    request.getfixturevalue(rung)
    page.goto(f"{frontend_base_url}{path}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(
        name=f"{name}.png",
        mask=default_masks(page),
        max_diff_pixel_ratio=0.02,
    )


# Per-id snapshots (threads + watchlists + snapshot-cost drill + thread-detail)
@pytest.mark.integration
@pytest.mark.visual
def test_watchlist_detail_snapshot(page: Page, frontend_base_url: str, market) -> None:
    from apps.market.models import Watchlist
    wl = Watchlist.objects.get(name="E2E Core")
    page.goto(f"{frontend_base_url}/watchlists/{wl.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(name="watchlist_detail.png",
                                    mask=default_masks(page), max_diff_pixel_ratio=0.02)


@pytest.mark.integration
@pytest.mark.visual
def test_thread_detail_plain_snapshot(page: Page, frontend_base_url: str, threads) -> None:
    from apps.threads.models import Thread
    t = Thread.objects.get(title="E2E plain thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(name="thread_detail_plain.png",
                                    mask=default_masks(page), max_diff_pixel_ratio=0.02)


@pytest.mark.integration
@pytest.mark.visual
def test_thread_detail_compare_snapshot(page: Page, frontend_base_url: str, threads) -> None:
    from apps.threads.models import Thread
    t = Thread.objects.get(title="E2E compare thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(name="thread_detail_compare.png",
                                    mask=default_masks(page), max_diff_pixel_ratio=0.02)


@pytest.mark.integration
@pytest.mark.visual
def test_snapshot_cost_drill_snapshot(page: Page, frontend_base_url: str, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    s = Snapshot.objects.filter(status="ready").first()
    page.goto(f"{frontend_base_url}/costs/snapshot/{s.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(name="snapshot_cost_drill.png",
                                    mask=default_masks(page), max_diff_pixel_ratio=0.02)


@pytest.mark.integration
@pytest.mark.visual
def test_observer_timeline_snapshot(page: Page, frontend_base_url: str, observer) -> None:
    from apps.profiles.models import TradingProfile
    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(name="observer_timeline.png",
                                    mask=default_masks(page), max_diff_pixel_ratio=0.02)


@pytest.mark.integration
@pytest.mark.visual
def test_snapshot_composer_with_ready_snap(page: Page, frontend_base_url: str, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    s = Snapshot.objects.filter(status="ready").first()
    page.goto(f"{frontend_base_url}/snapshot?pinned={s.id}")
    wait_for_stable(page)
    expect(page).to_have_screenshot(name="snapshot_composer_with_snap.png",
                                    mask=default_masks(page), max_diff_pixel_ratio=0.02)
```

- [ ] **Step 2: Generate baselines**

```bash
make e2e-visual-update
```

Inspect the diff:

```bash
git status e2e/visual/__screenshots__/
```

- [ ] **Step 3: Commit baselines + test file**

```bash
git add e2e/visual/test_route_snapshots.py e2e/visual/__screenshots__/
git commit -m "$(cat <<'EOF'
feat(e2e/visual): 20 page-level screenshot baselines

One baseline per top-level route plus id-specific variants (watchlist
detail, thread detail plain/compare, snapshot-cost drill, observer
timeline, snapshot composer w/ snap).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — Pre-commit size-guard hook

**Files:**
- Create: `tools/hooks/check_visual_baseline_size.sh`
- Modify: `.pre-commit-config.yaml`

- [ ] **Step 1: Test the guard**

Create `e2e/tests/test_baseline_size_guard.py`:

```python
"""Enforces ≤500KB per visual baseline."""
from __future__ import annotations

from pathlib import Path


def test_no_baseline_exceeds_500kb() -> None:
    root = Path("e2e/visual/__screenshots__")
    if not root.exists():
        return  # nothing to check
    oversize = [p for p in root.rglob("*.png") if p.stat().st_size > 500 * 1024]
    assert not oversize, f"baselines exceeding 500KB: {[str(p) for p in oversize]}"
```

- [ ] **Step 2: Run + pass (should be green if baselines are sensible).**

- [ ] **Step 3: Write the shell guard**

Create `tools/hooks/check_visual_baseline_size.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

max_kb=500
found_large=""

while read -r file; do
  [[ -z "$file" ]] && continue
  size_kb=$(( $(stat -c '%s' "$file") / 1024 ))
  if (( size_kb > max_kb )); then
    found_large+="$file ($size_kb KB)\n"
  fi
done < <(git diff --cached --name-only --diff-filter=AM | grep '^e2e/visual/__screenshots__/.*\.png$' || true)

if [[ -n "$found_large" ]]; then
  echo "Visual baselines exceed ${max_kb}KB limit:" >&2
  printf "%b" "$found_large" >&2
  exit 1
fi
```

`chmod +x tools/hooks/check_visual_baseline_size.sh`.

- [ ] **Step 4: Wire into `.pre-commit-config.yaml`** (create if absent)

```yaml
repos:
  - repo: local
    hooks:
      - id: visual-baseline-size
        name: Visual baseline ≤500KB
        entry: tools/hooks/check_visual_baseline_size.sh
        language: system
        pass_filenames: false
```

- [ ] **Step 5: Commit**

```bash
git add tools/hooks/check_visual_baseline_size.sh .pre-commit-config.yaml e2e/tests/test_baseline_size_guard.py
git commit -m "chore(e2e/visual): pre-commit size guard (≤500KB per baseline)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 — Document update flow in README

**Files:**
- Modify: `e2e/README.md`

- [ ] **Step 1: Append "Updating visual baselines" section**

Append to `e2e/README.md`:

```markdown

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

Baselines are capped at 500KB each — pre-commit will block oversized ones.
If you hit the cap, the problem is usually a mask leak; check that noisy
dynamic regions (timestamps, chart tooltips, notification counts) are
masked in `helpers/visual.py`.
```

- [ ] **Step 2: Commit**

```bash
git add e2e/README.md
git commit -m "docs(e2e): visual baseline update flow

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 acceptance

- [ ] `make e2e-visual` — 20 baselines present, all pass, wall time ≤ 6 min.
- [ ] Every baseline ≤ 500KB (`pytest e2e/tests/test_baseline_size_guard.py`).
- [ ] `make e2e-visual-update` regenerates baselines and prints diff summary.
- [ ] `.gitattributes` marks PNGs under `__screenshots__/` as binary.
- [ ] Pre-commit hook blocks oversized baselines.
- [ ] No regressions in other lanes.
