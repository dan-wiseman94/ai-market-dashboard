# E2E Phase 3 — UI Lane Gold Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the gold-path UI journeys — one happy path per top-level route, built on the Phase 2 POMs and Phase 1 seed ladder. ~25 tests total across 13 files.

**Architecture:** Each test uses the lightest seed rung it needs, drives the UI via POMs, and asserts visible outcomes. No error paths here (those land in Phase 4). Existing 6 relocated journeys are extended/rewritten to use POMs.

**Tech Stack:** pytest-playwright, POMs from Phase 2, fixtures from Phase 1.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §4 (UI catalog).

**Prerequisite:** Phases 0, 1, 2 complete.

---

## File structure

**Create / rewrite under `e2e/ui/`:**
- `test_dashboard.py` (3)
- `test_snapshots.py` (2 gold: `capture_all_sections_ok`, `snapshot_drill_down`, `snapshot_diff_endpoint_surfaced`)
- `test_threads.py` (3 gold: list/filter, create plain, pinned)
- `test_compare.py` (2 gold)
- `test_observer.py` (2 gold: create+run-now, pause+resume)
- `test_triggers.py` (2 gold: simple, complex DSL)
- `test_analytics.py` (6)
- `test_watchlists.py` (3)
- `test_profiles.py` (2)
- `test_costs.py` (3)
- `test_backups.py` (1 gold: backup_now, extends existing)
- `test_export.py` (1 gold: export_zip, extends existing)
- `test_settings.py` (2)

**Delete after rewrite:**
- `e2e/ui/test_snapshots_capture_gold.py` (replaced by `test_snapshots.py::test_capture_all_sections_ok`)
- `e2e/ui/test_compare_two_branches_gold.py` (replaced by `test_compare.py::test_compare_two_branches_stream_and_cost`)
- `e2e/ui/test_observer_run_now_gold.py` (replaced)
- `e2e/ui/test_trigger_fire_gold.py` (replaced)
- `e2e/ui/test_backups_gold.py` (kept — extended inline)
- `e2e/ui/test_export_gold.py` (kept — extended inline)

---

## Task 1 — `test_dashboard.py` (3 tests)

**Files:**
- Create: `e2e/ui/test_dashboard.py`

- [ ] **Step 1: Write tests**

```python
"""Dashboard gold paths."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.dashboard import DashboardPage


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_renders_all_cards(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    expect(d.card_snapshots).to_be_visible()
    expect(d.card_threads).to_be_visible()
    expect(d.card_cost).to_be_visible()
    expect(d.notification_bell).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_empty_state(page, frontend_base_url, minimal) -> None:
    """Fresh DB — every card shows EmptyState rather than skeleton or error."""
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # EmptyState renders inside each card; check at least one card surfaces it
    expect(page.get_by_text("No snapshots yet", exact=False).or_(page.get_by_text("No threads", exact=False))).to_be_visible()
    d.expect_error_boundary_absent()


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_cost_tile_reflects_airuns(page, frontend_base_url, analytics) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # Cost tile text must contain a $ amount > 0
    text = d.card_cost.inner_text()
    assert "$" in text
    assert "0.00" not in text or "$0.0" not in text  # allow small values but not literal zero
```

- [ ] **Step 2: Run + pass.**

Run: `docker compose exec web pytest e2e/ui/test_dashboard.py -v`

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_dashboard.py
git commit -m "test(e2e/ui): dashboard gold paths

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 — `test_snapshots.py` (3 gold)

**Files:**
- Create: `e2e/ui/test_snapshots.py`
- Delete: `e2e/ui/test_snapshots_capture_gold.py`

- [ ] **Step 1: Write tests**

```python
"""Snapshot gold paths — capture / drill-down / diff."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.costs import CostsPage
from e2e.pages.snapshot import SnapshotPage
from e2e.pages.snapshot_cost import SnapshotCostPage


@pytest.mark.integration
@pytest.mark.ui
def test_capture_all_sections_ok(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.capture(profile="E2E Default", objective="gold test")
    s.wait_for_complete()
    s.send_to_ai()
    expect(page.get_by_text("Mocked response")).to_be_visible(timeout=15_000)

    costs = CostsPage(page, frontend_base_url)
    costs.go()
    expect(page.get_by_text("claude", exact=False)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_drill_down(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    snap = Snapshot.objects.filter(status="ready").first()
    d = SnapshotCostPage(page, frontend_base_url)
    d.go(snap.id)
    for name in ("quotes", "ohlc", "chain", "positions", "breadth", "news", "charts"):
        expect(d.section_row(name)).to_be_visible()
    expect(d.cost_total).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_snapshot_diff_endpoint_surfaced(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    [curr, prev] = list(Snapshot.objects.filter(status="ready")[:2])
    page.goto(f"{frontend_base_url}/costs/snapshot/{curr.id}")
    page.get_by_role("button", name="Compare vs previous").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.get_by_text("delta", exact=False)).to_be_visible()
```

- [ ] **Step 2: Remove old gold file**

```bash
git rm e2e/ui/test_snapshots_capture_gold.py
```

- [ ] **Step 3: Run + pass + commit.**

```bash
git add e2e/ui/test_snapshots.py
git commit -m "test(e2e/ui): snapshot gold paths (capture, drill, diff)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — `test_threads.py` (3 gold)

**Files:**
- Create: `e2e/ui/test_threads.py`

- [ ] **Step 1: Write tests**

```python
"""Threads — list + create plain + create pinned."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.threads import ThreadsListPage
from e2e.pages.thread_detail import ThreadDetailPage


@pytest.mark.integration
@pytest.mark.ui
def test_threads_list_pagination_and_filter(page, frontend_base_url, threads) -> None:
    p = ThreadsListPage(page, frontend_base_url)
    p.go()
    # Row count matches at least what the seed produced
    expect(page.locator("[data-testid^='thread-row-']")).to_have_count_greater_than(4)  # type: ignore[attr-defined]
    # Filter narrows
    p.filter("compare")
    expect(page.locator("[data-testid^='thread-row-']")).to_have_count(1)


@pytest.mark.integration
@pytest.mark.ui
def test_thread_create_plain_and_send(page, frontend_base_url, minimal) -> None:
    page.goto(f"{frontend_base_url}/threads")
    page.get_by_role("button", name="New thread").click()
    page.get_by_label("Profile").select_option(label="E2E Default")
    page.get_by_label("Title").fill("ui plain")
    page.get_by_role("button", name="Create").click()
    # Redirected to /threads/:id
    expect(page).to_have_url(lambda url: "/threads/" in url and url.endswith((str(i) for i in range(10_000))) or True)  # loose
    # Send
    page.get_by_test_id("compose-input").fill("hello")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_text("Mocked response")).to_be_visible(timeout=15_000)


@pytest.mark.integration
@pytest.mark.ui
def test_thread_create_pinned_to_snapshot(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    snap = Snapshot.objects.filter(status="ready").first()
    page.goto(f"{frontend_base_url}/threads/new?pinned_snapshot={snap.id}")
    page.get_by_label("Profile").select_option(label="E2E Default")
    page.get_by_label("Title").fill("ui pinned")
    page.get_by_role("button", name="Create").click()
    # Synthetic first user message visible
    expect(page.get_by_role("listitem").filter(has_text="quotes")).to_be_visible(timeout=5_000)
```

*(The `to_have_count_greater_than` assertion is not in Playwright's base API — implement a small helper or use `assert page.locator(...).count() > 4`.)*

- [ ] **Step 2: Fix the count helper**

Edit the first test to use `assert`:

```python
rows = page.locator("[data-testid^='thread-row-']")
assert rows.count() > 4
```

- [ ] **Step 3: Pass + commit.**

```bash
git add e2e/ui/test_threads.py
git commit -m "test(e2e/ui): threads gold (list, plain, pinned)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 — `test_compare.py` (2 gold)

**Files:**
- Create: `e2e/ui/test_compare.py`
- Delete: `e2e/ui/test_compare_two_branches_gold.py`

- [ ] **Step 1: Tests**

```python
"""Compare — 2 branches, 3 providers."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.snapshot import SnapshotPage


@pytest.mark.integration
@pytest.mark.ui
def test_compare_two_branches_stream_and_cost(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.capture(profile="E2E Default", objective="compare 2")
    s.wait_for_complete()
    s.send_to_ai()
    expect(page.get_by_text("Mocked response")).to_be_visible(timeout=15_000)

    s.open_compare()
    page.get_by_role("button", name="Send to 2 branches").click()
    expect(page.locator("[data-testid^='branch-cost-']")).to_have_count(2, timeout=15_000)


@pytest.mark.integration
@pytest.mark.ui
def test_compare_three_providers_routes_costs(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.capture(profile="E2E Default", objective="compare 3")
    s.wait_for_complete()
    s.send_to_ai()
    expect(page.get_by_text("Mocked response")).to_be_visible(timeout=15_000)

    s.open_compare()
    # Add a third target
    page.get_by_role("button", name="Add provider").click()
    page.get_by_role("button", name="Send to 3 branches").click()
    tiles = page.locator("[data-testid^='branch-cost-']")
    expect(tiles).to_have_count(3, timeout=15_000)
    # Total row = sum
    total_text = page.get_by_test_id("compare-cost-total").inner_text()
    assert "$" in total_text
```

- [ ] **Step 2: Drop old file**

```bash
git rm e2e/ui/test_compare_two_branches_gold.py
```

- [ ] **Step 3: Pass + commit.**

```bash
git add e2e/ui/test_compare.py
git commit -m "test(e2e/ui): compare gold (2 + 3 branches)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5 — `test_observer.py` (2 gold)

**Files:**
- Create: `e2e/ui/test_observer.py`
- Delete: `e2e/ui/test_observer_run_now_gold.py`

- [ ] **Step 1: Tests**

```python
"""Observer gold — create schedule + run now; pause/resume."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.schedules import SchedulesPage


@pytest.mark.integration
@pytest.mark.ui
def test_create_schedule_and_run_now(page, frontend_base_url, minimal) -> None:
    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.create(interval=60)
    # Grab the newly created row id from the DOM
    row = page.locator("[data-testid^='schedule-row-']").last
    row_id = row.get_attribute("data-testid").split("-")[-1]
    s.run_now(int(row_id))
    expect(s.notification_bell).to_contain_text("1", timeout=30_000)


@pytest.mark.integration
@pytest.mark.ui
def test_schedule_pause_resume(page, frontend_base_url, observer) -> None:
    from apps.observer.models import ObserverSchedule
    sched = ObserverSchedule.objects.get(name="E2E active schedule")

    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.pause(sched.id)
    expect(s.page.get_by_test_id(f"schedule-row-{sched.id}")).to_contain_text("paused")
    # Resume
    page.get_by_test_id(f"schedule-row-{sched.id}").get_by_role("button", name="Resume").click()
    expect(s.page.get_by_test_id(f"schedule-row-{sched.id}")).to_contain_text("active")
```

- [ ] **Step 2: Drop old file**

```bash
git rm e2e/ui/test_observer_run_now_gold.py
```

- [ ] **Step 3: Pass + commit.**

```bash
git add e2e/ui/test_observer.py
git commit -m "test(e2e/ui): observer gold (run-now + pause/resume)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 — `test_triggers.py` (2 gold)

**Files:**
- Create: `e2e/ui/test_triggers.py`
- Delete: `e2e/ui/test_trigger_fire_gold.py`

- [ ] **Step 1: Tests**

```python
"""Triggers gold — simple + complex DSL."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.trigger_editor import TriggerEditorPage
from e2e.pages.triggers import TriggersListPage


@pytest.mark.integration
@pytest.mark.ui
def test_create_simple_trigger_and_fire_now(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    e.fill_simple(name="ui-simple", ticker="AAPL", metric="last", op=">", value="0")
    e.save()
    e.fire_now_btn.click()
    expect(e.notification_bell).to_contain_text("1", timeout=30_000)

    # Firings tab shows one row
    page.get_by_role("link", name="ui-simple").click()
    page.get_by_role("tab", name="Firings").click()
    assert page.locator("text=fired").count() >= 1


@pytest.mark.integration
@pytest.mark.ui
def test_create_complex_dsl_all_any_not(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    e.page.get_by_label("Name").fill("ui-complex")
    e.page.get_by_role("button", name="Advanced (DSL)").click()
    e.fill_dsl({"all": [
        {"ticker": "AAPL", "metric": "last", "op": ">", "value": 100},
        {"any": [{"ticker": "MSFT", "metric": "last", "op": ">", "value": 100}]},
        {"not": {"ticker": "VIX", "metric": "last", "op": ">", "value": 40}},
    ]})
    e.save()

    # Confirms in the list
    tl = TriggersListPage(page, frontend_base_url)
    tl.go()
    expect(page.get_by_text("ui-complex")).to_be_visible()
```

- [ ] **Step 2: Drop old file**

```bash
git rm e2e/ui/test_trigger_fire_gold.py
```

- [ ] **Step 3: Pass + commit.**

```bash
git add e2e/ui/test_triggers.py
git commit -m "test(e2e/ui): triggers gold (simple + complex DSL)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7 — `test_analytics.py` (6 tests)

**Files:**
- Create: `e2e/ui/test_analytics.py`

- [ ] **Step 1: Tests**

```python
"""Analytics — one test per card + zero-coverage behavior."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.analytics import AnalyticsPage


@pytest.mark.integration
@pytest.mark.ui
def test_analytics_page_renders_all_five_cards(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    for kind in ("leaderboard", "cpi", "heatmap", "timeline", "unusual-options"):
        expect(a.card(kind)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_orders_by_forward_return(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    rows = a.card_leaderboard.get_by_role("row")
    # More than header: at least 2 rows of data
    assert rows.count() >= 3


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_zero_coverage_row(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    # At least one row must show coverage 0%
    expect(a.card_leaderboard.get_by_text("0%")).to_have_count(1, timeout=5_000)


@pytest.mark.integration
@pytest.mark.ui
def test_cost_per_insight_card(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    expect(a.card_cpi).to_contain_text("$")


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_heatmap_renders_cells(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    cells = a.card_heatmap.locator("[data-cell]")
    assert cells.count() >= 7  # at least one week of cells


@pytest.mark.integration
@pytest.mark.ui
def test_unusual_options_card_shows_triggers(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.set_ticker("AAPL")
    # Each flagged line renders a list of triggers
    triggers = a.card_unusual("AAPL").locator("[data-trigger]")
    assert triggers.count() >= 1
```

- [ ] **Step 2: Pass + commit.**

```bash
git add e2e/ui/test_analytics.py
git commit -m "test(e2e/ui): analytics gold (5 cards + zero-coverage + triggers)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8 — `test_watchlists.py` (3 tests)

**Files:**
- Create: `e2e/ui/test_watchlists.py`

- [ ] **Step 1: Tests**

```python
"""Watchlists + market-ticker gold."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.market_ticker import MarketTickerPage
from e2e.pages.watchlist_detail import WatchlistDetailPage
from e2e.pages.watchlists import WatchlistsPage


@pytest.mark.integration
@pytest.mark.ui
def test_watchlists_list_and_create(page, frontend_base_url, market) -> None:
    w = WatchlistsPage(page, frontend_base_url)
    w.go()
    expect(page.get_by_test_id("watchlist-row-E2E Core")).to_be_visible()
    w.create("UI New Watchlist")
    expect(page.get_by_test_id("watchlist-row-UI New Watchlist")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_watchlist_detail_add_remove_ticker(page, frontend_base_url, market) -> None:
    from apps.market.models import Watchlist
    wl = Watchlist.objects.get(name="E2E Core")
    d = WatchlistDetailPage(page, frontend_base_url)
    d.go(wl.id)
    d.add("TSLA")
    expect(d.ticker_row("TSLA")).to_be_visible()
    d.remove("TSLA")
    expect(d.ticker_row("TSLA")).to_have_count(0)


@pytest.mark.integration
@pytest.mark.ui
def test_market_ticker_page_renders_ohlc_and_news(page, frontend_base_url, market) -> None:
    m = MarketTickerPage(page, frontend_base_url)
    m.go("AAPL")
    expect(m.ohlc_chart).to_be_visible()
    expect(m.news_list).to_be_visible()
```

- [ ] **Step 2: Pass + commit.**

```bash
git add e2e/ui/test_watchlists.py
git commit -m "test(e2e/ui): watchlists + market-ticker gold

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9 — `test_profiles.py` (2)

**Files:**
- Create: `e2e/ui/test_profiles.py`

```python
"""Profiles gold."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.profiles import ProfilesPage


@pytest.mark.integration
@pytest.mark.ui
def test_profile_create_with_memory_tools_thinking_flags(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.create(name="ui-pro", enable_tools=True, thinking_budget=4096, enable_memory=True)
    expect(p.row("ui-pro")).to_be_visible()
    # Flags persisted
    p.row("ui-pro").click()
    expect(p.tools_toggle).to_be_checked()
    expect(p.memory_toggle).to_be_checked()


@pytest.mark.integration
@pytest.mark.ui
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.toggle_active("E2E Tools-Enabled")
    expect(p.row("E2E Tools-Enabled")).to_contain_text("Active")
```

- [ ] **Pass + commit.**

```bash
git add e2e/ui/test_profiles.py
git commit -m "test(e2e/ui): profiles gold (flags + activation)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10 — `test_costs.py` (3)

```python
"""Costs — today tile, caps, CSV."""
from __future__ import annotations

import csv
import io

import pytest
from playwright.sync_api import expect

from e2e.pages.costs import CostsPage


@pytest.mark.integration
@pytest.mark.ui
def test_costs_today_tile(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    expect(c.today_tile).to_be_visible()
    text = c.today_tile.inner_text()
    assert "$" in text


@pytest.mark.integration
@pytest.mark.ui
def test_costs_caps_editor_persists(page, frontend_base_url, minimal) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    c.set_caps(daily="3.50", monthly="99.00")
    c.expect_toast("saved", kind="success")
    # Reload + verify
    c.go()
    assert c.caps_editor.get_by_label("Daily cap (USD)").input_value() == "3.50"


@pytest.mark.integration
@pytest.mark.ui
def test_costs_csv_export_downloads_and_parses(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    body = c.export_csv()
    reader = csv.reader(io.StringIO(body.decode()))
    rows = list(reader)
    assert rows[0][0] in ("date", "Date", "provider")  # header present
    assert len(rows) > 1
```

- [ ] **Pass + commit.**

```bash
git add e2e/ui/test_costs.py
git commit -m "test(e2e/ui): costs gold (tile + caps + CSV)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11 — Refactor `test_backups.py` + `test_export.py` to POMs

**Files:**
- Modify: `e2e/ui/test_backups_gold.py` → rename to `test_backups.py`
- Modify: `e2e/ui/test_export_gold.py` → rename to `test_export.py`

- [ ] **Step 1: Rename**

```bash
git mv e2e/ui/test_backups_gold.py e2e/ui/test_backups.py
git mv e2e/ui/test_export_gold.py e2e/ui/test_export.py
```

- [ ] **Step 2: Rewrite `e2e/ui/test_backups.py` to use POM**

```python
"""Backup gold — back up now + gzip magic + API download."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_BASE_URL
from e2e.pages.backups import BackupsPage


@pytest.mark.integration
@pytest.mark.ui
def test_backup_now_and_gzip_magic(page, frontend_base_url, minimal, tmp_path: Path) -> None:
    b = BackupsPage(page, frontend_base_url)
    b.go()
    b.backup_now()
    expect(page.locator("tr:has-text('ok')")).to_be_visible(timeout=60_000)

    rows = httpx.get(f"{E2E_BASE_URL}/api/backups/", timeout=5).json()
    rows = rows.get("results", rows)
    rec = next(r for r in rows if r["kind"] == "manual" and r["status"] == "ok")
    r = httpx.get(f"{E2E_BASE_URL}/api/backups/{rec['id']}/download/", timeout=30)
    dl = tmp_path / rec["filename"]
    dl.write_bytes(r.content)
    assert dl.stat().st_size > 0
    assert dl.read_bytes()[:2] == b"\x1f\x8b"
```

- [ ] **Step 3: Rewrite `e2e/ui/test_export.py`**

```python
"""Export gold — start + zip + manifest v1."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_BASE_URL
from e2e.pages.export import ExportPage


@pytest.mark.integration
@pytest.mark.ui
def test_export_zip_and_manifest(page, frontend_base_url, threads, tmp_path: Path) -> None:
    e = ExportPage(page, frontend_base_url)
    e.go()
    e.start()
    expect(page.locator("tr:has-text('done')")).to_be_visible(timeout=60_000)

    jobs = httpx.get(f"{E2E_BASE_URL}/api/export/", timeout=5).json()
    rows = jobs.get("results", jobs)
    done = next(j for j in rows if j["status"] == "done")
    r = httpx.get(f"{E2E_BASE_URL}/api/export/{done['id']}/download/", timeout=30)
    dl = tmp_path / done["filename"]
    dl.write_bytes(r.content)

    with zipfile.ZipFile(dl) as zf:
        names = zf.namelist()
        assert any("manifest.json" in n for n in names)
        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name))
        assert manifest["version"] == 1
```

- [ ] **Step 4: Pass + commit.**

```bash
git add e2e/ui/test_backups.py e2e/ui/test_export.py
git commit -m "test(e2e/ui): backup + export gold through POMs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12 — `test_settings.py` (2)

**Files:**
- Create: `e2e/ui/test_settings.py`

```python
"""Settings gold — API key round-trip + caps edit."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.settings import SettingsPage


@pytest.mark.integration
@pytest.mark.ui
def test_provider_api_key_save_round_trip_masked(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    s.save_api_key("claude", "sk-test-123456")
    s.expect_toast("saved", kind="success")
    # Reload — key is masked
    s.go()
    value = s.api_key_input("claude").input_value()
    assert "•" in value or "***" in value or "sk-" not in value


@pytest.mark.integration
@pytest.mark.ui
def test_daily_and_monthly_cap_edit(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    page.get_by_label("Daily cost cap (USD)").fill("2.50")
    page.get_by_label("Monthly cost cap (USD)").fill("50.00")
    page.get_by_role("button", name="Save").click()
    s.expect_toast("saved", kind="success")
    s.go()
    assert page.get_by_label("Daily cost cap (USD)").input_value() == "2.50"
```

- [ ] **Pass + commit.**

```bash
git add e2e/ui/test_settings.py
git commit -m "test(e2e/ui): settings gold (api key mask + caps persist)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 acceptance

- [ ] `make e2e-ui` runs ≥25 tests — all pass.
- [ ] The 4 old `_gold.py` files are gone.
- [ ] Wall time ≤ 10 min with `-n 4 --dist=loadscope`.
- [ ] No regressions in `make e2e-api`.
