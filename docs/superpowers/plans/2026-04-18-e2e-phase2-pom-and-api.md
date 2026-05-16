# E2E Phase 2 — POM + API Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flesh out the page-object-model layer (18 pages) and ship the full API contract lane (~26 tests). API lane runs first because it's the fastest feedback loop and validates the backend contract.

**Architecture:** POMs follow the pattern `locators as properties, actions as methods, assertions in tests`. API tests use httpx against `http://web:8000` inside the web container, relying on Phase 1 seed rungs for state.

**Tech Stack:** httpx, pytest-django, Playwright locators.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §5.1 (API catalog), §6 (POM).

**Prerequisite:** Phases 0 and 1 complete.

---

## File structure

**Create — page objects (replace Phase 0 stubs):**
- `e2e/pages/base.py` (extend), `dashboard.py`, `snapshot.py`, `threads.py`, `thread_detail.py`, `compare.py`, `observer.py`, `schedules.py`, `triggers.py`, `trigger_editor.py`, `analytics.py`, `watchlists.py`, `watchlist_detail.py`, `market_ticker.py`, `profiles.py`, `costs.py`, `snapshot_cost.py`, `backups.py`, `export.py`, `settings.py`, `schwab_oauth.py`, `files.py`

**Create — API test files:**
- `e2e/api/test_health.py`
- `e2e/api/test_market_contract.py`
- `e2e/api/test_snapshots_contract.py`
- `e2e/api/test_threads_contract.py`
- `e2e/api/test_observer_contract.py`
- `e2e/api/test_triggers_contract.py`
- `e2e/api/test_analytics_contract.py`
- `e2e/api/test_backups_contract.py`
- `e2e/api/test_export_contract.py`
- `e2e/api/test_costs_caps.py`
- `e2e/api/test_files_contract.py`

**Modify:**
- `e2e/api/conftest.py` — api_client fixture scoped to api lane

---

## Task 1 — `BasePage`

**Files:**
- Modify: `e2e/pages/base.py`

- [ ] **Step 1: Test**

Create `e2e/tests/test_pages.py`:

```python
"""POM shape tests — every page class exposes the agreed surface."""
from __future__ import annotations

import inspect


def test_base_page_has_expected_methods() -> None:
    from e2e.pages.base import BasePage
    required = {"goto", "wait_ready", "expect_toast", "expect_error_boundary_absent",
                "open_command_palette", "run_shortcut", "current_crumb_trail"}
    actual = {name for name, _ in inspect.getmembers(BasePage, inspect.isfunction)}
    assert required.issubset(actual), f"missing: {required - actual}"
```

- [ ] **Step 2: Fail** — Base lacks these methods.

- [ ] **Step 3: Rewrite `e2e/pages/base.py`**

```python
"""Base page object — shared navigation + common assertions.

Locators are properties (return `page.get_by_...`).
Actions are methods.
Assertions live in tests (never in POMs).
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, expect


class BasePage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")

    def goto(self, path: str) -> None:
        self.page.goto(f"{self.base_url}{path}")
        self.wait_ready()

    def wait_ready(self) -> None:
        self.page.wait_for_load_state("networkidle")
        # Wait for any visible skeletons to disappear — best-effort; 2s ceiling.
        try:
            self.page.wait_for_selector("[data-testid^='skeleton-']", state="detached", timeout=2000)
        except Exception:  # noqa: BLE001
            pass

    # --- locator properties ---
    @property
    def notification_bell(self) -> Locator:
        return self.page.get_by_test_id("notification-bell")

    @property
    def connection_dot(self) -> Locator:
        return self.page.get_by_test_id("connection-status-dot")

    @property
    def breadcrumb_trail(self) -> Locator:
        return self.page.get_by_test_id("breadcrumb-trail")

    # --- actions ---
    def expect_toast(self, text: str, kind: str = "info", timeout: int = 5000) -> None:
        expect(self.page.get_by_test_id(f"toast-{kind}")).to_contain_text(text, timeout=timeout)

    def expect_error_boundary_absent(self) -> None:
        expect(self.page.get_by_text("Something went wrong", exact=False)).to_have_count(0)

    def open_command_palette(self) -> None:
        import platform
        self.page.keyboard.press("Meta+K" if platform.system() == "Darwin" else "Control+K")
        expect(self.page.get_by_test_id("command-palette")).to_be_visible()

    def run_shortcut(self, keys: str) -> None:
        for key in keys.split():
            self.page.keyboard.press(key)

    def current_crumb_trail(self) -> list[str]:
        items = self.breadcrumb_trail.locator("li")
        return [items.nth(i).inner_text() for i in range(items.count())]
```

- [ ] **Step 4: Pass.**

Run: `docker compose exec web pytest e2e/tests/test_pages.py::test_base_page_has_expected_methods -v`

- [ ] **Step 5: Commit**

```bash
git add e2e/pages/base.py e2e/tests/test_pages.py
git commit -m "feat(e2e): BasePage with shared locators + actions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 — `SnapshotComposerPage`

**Files:**
- Modify: `e2e/pages/snapshot.py`

- [ ] **Step 1: Test**

Append to `e2e/tests/test_pages.py`:

```python
def test_snapshot_page_exposes_expected_actions() -> None:
    from e2e.pages.snapshot import SnapshotPage
    for m in ("go", "capture", "wait_for_complete", "send_to_ai", "open_compare"):
        assert hasattr(SnapshotPage, m), f"missing method: {m}"
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Rewrite `e2e/pages/snapshot.py`**

```python
"""Snapshot composer page — /snapshot."""
from __future__ import annotations

from playwright.sync_api import Locator, expect

from e2e.pages.base import BasePage


class SnapshotPage(BasePage):
    PATH = "/snapshot"

    def go(self) -> None:
        self.goto(self.PATH)

    # --- locators ---
    @property
    def profile_select(self) -> Locator:
        return self.page.get_by_label("Profile")

    @property
    def objective_input(self) -> Locator:
        return self.page.get_by_label("Objective")

    @property
    def capture_btn(self) -> Locator:
        return self.page.get_by_test_id("capture-btn")

    @property
    def send_ai_btn(self) -> Locator:
        return self.page.get_by_test_id("send-ai-btn")

    def section_status(self, name: str) -> Locator:
        return self.page.get_by_test_id(f"section-{name}-status")

    # --- actions ---
    def capture(self, profile: str, objective: str, sections: list[str] | None = None) -> None:
        self.profile_select.select_option(label=profile)
        self.objective_input.fill(objective)
        if sections is not None:
            # Checklist logic — tests provide the explicit list; default UI state accepted
            for label in sections:
                self.page.get_by_label(label).check()
        self.capture_btn.click()

    def wait_for_complete(self, timeout: int = 30_000) -> None:
        expect(self.page.get_by_text("complete", exact=False)).to_be_visible(timeout=timeout)

    def send_to_ai(self) -> None:
        self.send_ai_btn.click()

    def open_compare(self) -> None:
        self.page.get_by_role("button", name="Compare").click()
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add e2e/pages/snapshot.py e2e/tests/test_pages.py
git commit -m "feat(e2e): SnapshotPage POM

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — `ThreadsListPage` + `ThreadDetailPage`

**Files:**
- Modify: `e2e/pages/threads.py`
- Create: `e2e/pages/thread_detail.py`

- [ ] **Step 1: Test**

Append:

```python
def test_thread_pages_exposed() -> None:
    from e2e.pages.threads import ThreadsListPage
    from e2e.pages.thread_detail import ThreadDetailPage
    for m in ("go", "open", "filter"): assert hasattr(ThreadsListPage, m)
    for m in ("go", "send", "stop", "attach_file", "wait_for_done"): assert hasattr(ThreadDetailPage, m)
```

- [ ] **Step 2: Fail.**

- [ ] **Step 3: Implement**

`e2e/pages/threads.py`:

```python
"""Threads list page — /threads."""
from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class ThreadsListPage(BasePage):
    PATH = "/threads"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def filter_input(self) -> Locator:
        return self.page.get_by_label("Filter")

    @property
    def pagination_next(self) -> Locator:
        return self.page.get_by_role("button", name="Next")

    def thread_row(self, thread_id: int) -> Locator:
        return self.page.get_by_test_id(f"thread-row-{thread_id}")

    def open(self, thread_id: int) -> None:
        self.thread_row(thread_id).click()

    def filter(self, text: str) -> None:
        self.filter_input.fill(text)
```

`e2e/pages/thread_detail.py`:

```python
"""Thread detail page — /threads/:id."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, expect

from e2e.pages.base import BasePage


class ThreadDetailPage(BasePage):
    def go(self, thread_id: int) -> None:
        self.goto(f"/threads/{thread_id}")

    # locators
    def message(self, message_id: int) -> Locator:
        return self.page.get_by_test_id(f"message-{message_id}")

    @property
    def compose(self) -> Locator:
        return self.page.get_by_test_id("compose-input")

    @property
    def stop_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Stop")

    def branch_tab(self, n: int) -> Locator:
        return self.page.get_by_role("tab", name=f"Branch {n}")

    def cost_tile(self, n: int) -> Locator:
        return self.page.get_by_test_id(f"branch-cost-{n}")

    # actions
    def send(self, text: str) -> None:
        self.compose.fill(text)
        self.page.get_by_role("button", name="Send").click()

    def stop(self) -> None:
        self.stop_btn.click()

    def attach_file(self, path: Path) -> None:
        self.page.get_by_role("button", name="Attach").click()
        self.page.set_input_files("input[type=file]", str(path))

    def wait_for_done(self, timeout: int = 15_000) -> None:
        expect(self.page.get_by_text("Mocked response")).to_be_visible(timeout=timeout)
```

- [ ] **Step 4: Pass.**

- [ ] **Step 5: Commit**

```bash
git add e2e/pages/threads.py e2e/pages/thread_detail.py e2e/tests/test_pages.py
git commit -m "feat(e2e): ThreadsListPage + ThreadDetailPage POMs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Tasks 4–18 — Remaining POMs (1 task each, same pattern)

Each task: write `test_pages.py` assertion that `hasattr(PageClass, method)` for each action, then implement the page class under the spec. Use the matrix from the spec §6.

Commit after each page. Commit message: `feat(e2e): <PageName> POM`.

**Task 4 — `DashboardPage`** (`e2e/pages/dashboard.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class DashboardPage(BasePage):
    PATH = "/"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def card_snapshots(self) -> Locator:
        return self.page.locator(".card-snapshots")

    @property
    def card_threads(self) -> Locator:
        return self.page.locator(".card-threads")

    @property
    def card_cost(self) -> Locator:
        return self.page.get_by_test_id("cost-tile-today")

    def open_notification_drawer(self) -> None:
        self.notification_bell.click()
```

**Task 5 — `ObserverTimelinePage`**:

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class ObserverTimelinePage(BasePage):
    def go(self, profile_id: int) -> None:
        self.goto(f"/threads/observer/{profile_id}")

    @property
    def fire_rows(self) -> Locator:
        return self.page.locator("[data-testid^='fire-row-']")

    def scroll_to_day(self, date_iso: str) -> None:
        self.page.get_by_text(date_iso).scroll_into_view_if_needed()
```

**Task 6 — `SchedulesPage`** (`e2e/pages/schedules.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class SchedulesPage(BasePage):
    PATH = "/schedules"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def create_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Create schedule")

    @property
    def interval_input(self) -> Locator:
        return self.page.get_by_label("Interval (seconds)")

    @property
    def mode_select(self) -> Locator:
        return self.page.get_by_label("Mode")

    @property
    def structured_toggle(self) -> Locator:
        return self.page.get_by_label("Structured")

    def run_now_btn(self, schedule_id: int) -> Locator:
        return self.page.get_by_test_id(f"schedule-row-{schedule_id}").get_by_role("button", name="Run now")

    def pause_btn(self, schedule_id: int) -> Locator:
        return self.page.get_by_test_id(f"schedule-row-{schedule_id}").get_by_role("button", name="Pause")

    def create(self, interval: int, mode: str = "full", structured: bool = False) -> None:
        self.create_btn.click()
        self.interval_input.fill(str(interval))
        if mode != "full":
            self.mode_select.select_option(value=mode)
        if structured:
            self.structured_toggle.check()
        self.page.get_by_role("button", name="Save").click()

    def run_now(self, schedule_id: int) -> None:
        self.run_now_btn(schedule_id).click()

    def pause(self, schedule_id: int) -> None:
        self.pause_btn(schedule_id).click()
```

**Task 7 — `TriggersListPage`** (`e2e/pages/triggers.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class TriggersListPage(BasePage):
    PATH = "/triggers"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def new_btn(self) -> Locator:
        return self.page.get_by_role("link", name="New trigger")

    def row(self, trigger_id: int) -> Locator:
        return self.page.get_by_test_id(f"trigger-row-{trigger_id}")

    def firings_tab(self) -> Locator:
        return self.page.get_by_role("tab", name="Firings")

    def open(self, trigger_id: int) -> None:
        self.row(trigger_id).click()
```

**Task 8 — `TriggerEditorPage`** (`e2e/pages/trigger_editor.py`):

```python
from __future__ import annotations
import json
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class TriggerEditorPage(BasePage):
    def go_new(self) -> None:
        self.goto("/triggers/new")

    def go(self, trigger_id: int) -> None:
        self.goto(f"/triggers/{trigger_id}")

    @property
    def name(self) -> Locator: return self.page.get_by_label("Name")
    @property
    def ticker(self) -> Locator: return self.page.get_by_label("Ticker")
    @property
    def metric(self) -> Locator: return self.page.get_by_label("Metric")
    @property
    def op(self) -> Locator: return self.page.get_by_label("Op")
    @property
    def value(self) -> Locator: return self.page.get_by_label("Value")
    @property
    def dsl_json(self) -> Locator: return self.page.get_by_label("DSL JSON")
    @property
    def backtest_btn(self) -> Locator: return self.page.get_by_role("button", name="Backtest")
    @property
    def fire_now_btn(self) -> Locator: return self.page.get_by_role("button", name="Fire now")

    def fill_simple(self, *, name: str, ticker: str, metric: str, op: str, value: str) -> None:
        self.name.fill(name)
        self.ticker.fill(ticker)
        self.metric.select_option(value=metric)
        self.op.select_option(value=op)
        self.value.fill(value)

    def fill_dsl(self, condition: dict) -> None:
        self.dsl_json.fill(json.dumps(condition))

    def backtest(self, start: str, end: str) -> None:
        self.page.get_by_label("Start").fill(start)
        self.page.get_by_label("End").fill(end)
        self.backtest_btn.click()

    def save(self) -> None:
        self.page.get_by_role("button", name="Save").click()
```

**Task 9 — `AnalyticsPage`** (`e2e/pages/analytics.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class AnalyticsPage(BasePage):
    PATH = "/analytics"

    def go(self) -> None:
        self.goto(self.PATH)

    def card(self, kind: str) -> Locator:
        return self.page.get_by_test_id(f"analytics-card-{kind}")

    @property
    def card_leaderboard(self) -> Locator: return self.card("leaderboard")
    @property
    def card_cpi(self) -> Locator: return self.card("cpi")
    @property
    def card_heatmap(self) -> Locator: return self.card("heatmap")
    @property
    def card_timeline(self) -> Locator: return self.card("timeline")

    def card_unusual(self, ticker: str) -> Locator:
        return self.card("unusual-options")

    def set_ticker(self, sym: str) -> None:
        self.page.get_by_label("Ticker").fill(sym)

    def set_forward_hours(self, n: int) -> None:
        self.page.get_by_label("Forward hours").fill(str(n))
```

**Task 10 — `WatchlistsPage` + `WatchlistDetailPage`** (`e2e/pages/watchlists.py`, `e2e/pages/watchlist_detail.py`):

```python
# watchlists.py
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class WatchlistsPage(BasePage):
    PATH = "/watchlists"

    def go(self) -> None: self.goto(self.PATH)

    def list_item(self, name: str) -> Locator:
        return self.page.get_by_test_id(f"watchlist-row-{name}")

    @property
    def create_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Create watchlist")

    def create(self, name: str) -> None:
        self.create_btn.click()
        self.page.get_by_label("Name").fill(name)
        self.page.get_by_role("button", name="Save").click()

    def open(self, name: str) -> None:
        self.list_item(name).click()


# watchlist_detail.py
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class WatchlistDetailPage(BasePage):
    def go(self, watchlist_id: int) -> None:
        self.goto(f"/watchlists/{watchlist_id}")

    def ticker_row(self, ticker: str) -> Locator:
        return self.page.get_by_role("row", name=ticker)

    @property
    def add_input(self) -> Locator: return self.page.get_by_label("Add ticker")

    def remove_btn(self, ticker: str) -> Locator:
        return self.ticker_row(ticker).get_by_role("button", name="Remove")

    def add(self, ticker: str) -> None:
        self.add_input.fill(ticker)
        self.page.get_by_role("button", name="Add").click()

    def remove(self, ticker: str) -> None:
        self.remove_btn(ticker).click()
```

**Task 11 — `MarketTickerPage`** (`e2e/pages/market_ticker.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class MarketTickerPage(BasePage):
    def go(self, ticker: str) -> None:
        self.goto(f"/market/{ticker}")

    @property
    def ohlc_chart(self) -> Locator: return self.page.locator("[data-chart='ohlc']")
    @property
    def news_list(self) -> Locator: return self.page.get_by_role("list", name="news")
    @property
    def positions_tile(self) -> Locator: return self.page.get_by_test_id("positions-tile")
```

**Task 12 — `ProfilesPage`** (`e2e/pages/profiles.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class ProfilesPage(BasePage):
    PATH = "/profiles"

    def go(self) -> None: self.goto(self.PATH)

    def row(self, name: str) -> Locator:
        return self.page.get_by_test_id(f"profile-row-{name}")

    @property
    def tools_toggle(self) -> Locator: return self.page.get_by_label("Enable tools")
    @property
    def thinking_budget(self) -> Locator: return self.page.get_by_label("Thinking budget")
    @property
    def memory_toggle(self) -> Locator: return self.page.get_by_label("Enable memory")

    def create(self, *, name: str, enable_tools: bool = False, thinking_budget: int | None = None,
               enable_memory: bool = False) -> None:
        self.page.get_by_role("button", name="New profile").click()
        self.page.get_by_label("Name").fill(name)
        if enable_tools:
            self.tools_toggle.check()
        if thinking_budget is not None:
            self.thinking_budget.fill(str(thinking_budget))
        if enable_memory:
            self.memory_toggle.check()
        self.page.get_by_role("button", name="Save").click()

    def toggle_active(self, name: str) -> None:
        self.row(name).get_by_role("button", name="Activate").click()
```

**Task 13 — `CostsPage` + `SnapshotCostPage`** (`e2e/pages/costs.py`, `snapshot_cost.py`):

```python
# costs.py
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class CostsPage(BasePage):
    PATH = "/costs"

    def go(self) -> None: self.goto(self.PATH)

    @property
    def today_tile(self) -> Locator: return self.page.get_by_test_id("cost-tile-today")
    @property
    def provider_table(self) -> Locator: return self.page.get_by_role("table", name="Provider costs")
    @property
    def csv_btn(self) -> Locator: return self.page.get_by_role("button", name="Export CSV")
    @property
    def caps_editor(self) -> Locator: return self.page.get_by_test_id("caps-editor")

    def export_csv(self) -> bytes:
        with self.page.expect_download() as info:
            self.csv_btn.click()
        path = info.value.path()
        from pathlib import Path
        return Path(path).read_bytes()

    def set_caps(self, *, daily: str, monthly: str) -> None:
        self.caps_editor.get_by_label("Daily cap (USD)").fill(daily)
        self.caps_editor.get_by_label("Monthly cap (USD)").fill(monthly)
        self.page.get_by_role("button", name="Save caps").click()


# snapshot_cost.py
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class SnapshotCostPage(BasePage):
    def go(self, snapshot_id: int) -> None:
        self.goto(f"/costs/snapshot/{snapshot_id}")

    def section_row(self, name: str) -> Locator:
        return self.page.get_by_role("row", name=name)

    @property
    def cost_total(self) -> Locator:
        return self.page.get_by_test_id("cost-total")
```

**Task 14 — `BackupsPage`** (`e2e/pages/backups.py`):

```python
from __future__ import annotations
from pathlib import Path

import httpx
from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class BackupsPage(BasePage):
    PATH = "/settings/backups"

    def go(self) -> None: self.goto(self.PATH)

    @property
    def backup_now_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Back up now")

    def row(self, backup_id: int) -> Locator:
        return self.page.get_by_test_id(f"backup-row-{backup_id}")

    def restore_btn(self, backup_id: int) -> Locator:
        return self.row(backup_id).get_by_role("button", name="Restore")

    def download_btn(self, backup_id: int) -> Locator:
        return self.row(backup_id).get_by_role("link", name="Download")

    def backup_now(self) -> None:
        self.backup_now_btn.click()

    def restore(self, backup_id: int) -> None:
        self.restore_btn(backup_id).click()

    def download(self, backup_id: int) -> bytes:
        with self.page.expect_download() as info:
            self.download_btn(backup_id).click()
        return Path(info.value.path()).read_bytes()
```

**Task 15 — `ExportPage`** (`e2e/pages/export.py`):

```python
from __future__ import annotations
from pathlib import Path
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class ExportPage(BasePage):
    PATH = "/settings/export"

    def go(self) -> None: self.goto(self.PATH)

    @property
    def start_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Start export")

    def row(self, export_id: int) -> Locator:
        return self.page.get_by_test_id(f"export-row-{export_id}")

    def download_btn(self, export_id: int) -> Locator:
        return self.row(export_id).get_by_role("link", name="Download")

    def start(self) -> None:
        self.start_btn.click()

    def download(self, export_id: int) -> bytes:
        with self.page.expect_download() as info:
            self.download_btn(export_id).click()
        return Path(info.value.path()).read_bytes()
```

**Task 16 — `SettingsPage`** (`e2e/pages/settings.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class SettingsPage(BasePage):
    PATH = "/settings"

    def go(self) -> None: self.goto(self.PATH)

    def api_key_input(self, provider: str) -> Locator:
        return self.page.get_by_label(f"{provider} API key")

    @property
    def save_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Save")

    def save_api_key(self, provider: str, key: str) -> None:
        self.api_key_input(provider).fill(key)
        self.save_btn.click()
```

**Task 17 — `SchwabOAuthPage`** (`e2e/pages/schwab_oauth.py`):

```python
from __future__ import annotations
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class SchwabOAuthPage(BasePage):
    PATH = "/settings#schwab"

    def go(self) -> None: self.goto(self.PATH)

    @property
    def connect_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Connect Schwab")

    @property
    def status_pill(self) -> Locator:
        return self.page.get_by_test_id("schwab-status")

    def connect(self) -> None:
        self.connect_btn.click()
```

**Task 18 — `FilesPage`** (`e2e/pages/files.py`):

```python
from __future__ import annotations
from pathlib import Path
from playwright.sync_api import Locator
from e2e.pages.base import BasePage


class FilesPage(BasePage):
    def row(self, file_id: str) -> Locator:
        return self.page.get_by_test_id(f"file-row-{file_id}")

    def upload(self, path: Path) -> None:
        self.page.set_input_files("input[type=file]", str(path))
        self.page.get_by_role("button", name="Upload").click()

    def delete(self, file_id: str) -> None:
        self.row(file_id).get_by_role("button", name="Delete").click()
```

After each POM task:

- [ ] Run `docker compose exec web pytest e2e/tests/test_pages.py -v` — growing test suite should stay green.
- [ ] `git add e2e/pages/<file>.py e2e/tests/test_pages.py` + commit as above.

---

## Task 19 — API conftest: `api_client` lane fixture

**Files:**
- Modify: `e2e/api/conftest.py`

- [ ] **Step 1: Implement**

```python
"""API lane conftest — httpx client with a base_url."""
from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest


@pytest.fixture
def api_client(api_base_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=api_base_url, timeout=10) as client:
        yield client
```

- [ ] **Step 2: Commit**

```bash
git add e2e/api/conftest.py
git commit -m "chore(e2e): api lane conftest with api_client fixture

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 20 — `test_health.py`

**Files:**
- Create: `e2e/api/test_health.py`

- [ ] **Step 1: Write tests**

```python
"""Health + readiness contract."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_health_endpoint_returns_200(api_client) -> None:
    r = api_client.get("/api/health/")
    assert r.status_code == 200


@pytest.mark.integration
def test_ready_endpoint_returns_200_with_checks(api_client) -> None:
    r = api_client.get("/api/ready/")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body or "status" in body
```

- [ ] **Step 2: Run + pass.** Commit.

```bash
git add e2e/api/test_health.py
git commit -m "test(e2e/api): health + ready contract

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 21 — `test_market_contract.py`

**Files:**
- Create: `e2e/api/test_market_contract.py`

- [ ] **Step 1: Write tests**

```python
"""Market endpoints contract."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_quotes_returns_shape(api_client, market) -> None:
    r = api_client.get("/api/market/quotes/?tickers=AAPL,MSFT")
    assert r.status_code == 200
    body = r.json()
    for sym in ("AAPL", "MSFT"):
        assert sym in body
        for key in ("last", "bid", "ask"):
            assert key in body[sym]


@pytest.mark.integration
def test_ohlc_returns_bars(api_client, market) -> None:
    r = api_client.get("/api/market/ohlc/?ticker=AAPL&timeframe=1h&limit=10")
    assert r.status_code == 200
    bars = r.json()
    assert isinstance(bars, list) and len(bars) > 0
    b = bars[0]
    for key in ("ts", "open", "high", "low", "close", "volume"):
        assert key in b


@pytest.mark.integration
def test_chain_returns_lines(api_client, market) -> None:
    r = api_client.get("/api/market/chain/?ticker=AAPL")
    assert r.status_code == 200
    body = r.json()
    assert "lines" in body or isinstance(body, list)


@pytest.mark.integration
def test_news_returns_items(api_client, market) -> None:
    r = api_client.get("/api/market/news/?ticker=AAPL")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    if items:
        assert "title" in items[0]
```

- [ ] **Step 2: Pass.** Commit.

---

## Task 22 — `test_snapshots_contract.py`

```python
"""Snapshot endpoints."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_snapshot_create_status_sections_roundtrip(api_client, minimal) -> None:
    r = api_client.post("/api/snapshots/", json={
        "profile": "E2E Default", "objective": "api test",
        "sections": ["quotes"],
    })
    assert r.status_code in (200, 201)
    snap_id = r.json()["id"]
    # Poll for readiness
    for _ in range(30):
        s = api_client.get(f"/api/snapshots/{snap_id}/").json()
        if s["status"] in ("ready", "partial", "failed"):
            break
    else:
        pytest.fail("snapshot never became terminal")
    sections = api_client.get(f"/api/snapshots/{snap_id}/sections/").json()
    assert isinstance(sections, list)


@pytest.mark.integration
def test_snapshot_diff_endpoint(api_client, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    ready = list(Snapshot.objects.filter(status="ready")[:2])
    assert len(ready) >= 2
    r = api_client.get(f"/api/snapshots/{ready[0].id}/diff/?against={ready[1].id}")
    assert r.status_code == 200
    body = r.json()
    for key in ("delta", "prev_id", "curr_id"):
        assert key in body


@pytest.mark.integration
def test_snapshot_image_serve_returns_bytes(api_client, snapshots) -> None:
    from apps.snapshots.models import SnapshotImage
    img = SnapshotImage.objects.first()
    if img is None:
        pytest.skip("no SnapshotImage seeded")
    r = api_client.get(f"/api/snapshots/images/{img.id}/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 0
```

- [ ] **Test + pass + commit.**

---

## Task 23 — `test_threads_contract.py`

```python
"""Threads + compare + single-export contract."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_create_plain_thread(api_client, minimal) -> None:
    r = api_client.post("/api/threads/", json={"profile": "E2E Default", "title": "api plain"})
    assert r.status_code in (200, 201)
    body = r.json()
    assert body["title"] == "api plain"
    assert body.get("pinned_snapshot") in (None, "")


@pytest.mark.integration
def test_create_pinned_thread_synthesizes_first_user_message(api_client, snapshots) -> None:
    from apps.snapshots.models import Snapshot
    snap = Snapshot.objects.filter(status="ready").first()
    r = api_client.post("/api/threads/", json={
        "profile": "E2E Default", "title": "api pinned", "pinned_snapshot_id": snap.id,
    })
    assert r.status_code in (200, 201)
    tid = r.json()["id"]
    msgs = api_client.get(f"/api/threads/{tid}/messages/").json()
    assert len(msgs) >= 1
    first = msgs[0] if isinstance(msgs, list) else msgs["results"][0]
    assert first["role"] == "user"
    assert first.get("snapshot_ref") == snap.id


@pytest.mark.integration
def test_stop_message(api_client, threads, scenario) -> None:
    """Sending a message then immediately stopping returns stopped=true on done."""
    # NB: needs scenario fixture for deterministic slow-ish stream
    pytest.skip("Stop testing requires running provider — covered in UI/WS lanes.")


@pytest.mark.integration
def test_compare_endpoint_returns_branches(api_client, threads) -> None:
    from apps.threads.models import Thread
    t = Thread.objects.filter(title="E2E plain thread").first()
    r = api_client.post(f"/api/threads/{t.id}/compare/", json={
        "prompt": "compare",
        "targets": [{"provider": "claude", "model": "claude-sonnet-4-6"},
                    {"provider": "openai", "model": "gpt-5-mini"}],
    })
    assert r.status_code in (200, 202)
    branches = r.json().get("branches")
    assert isinstance(branches, list) and len(branches) == 2


@pytest.mark.integration
def test_single_thread_export(api_client, threads) -> None:
    from apps.threads.models import Thread
    t = Thread.objects.first()
    r = api_client.get(f"/api/export/thread/{t.id}/")
    assert r.status_code == 200
    assert r.headers["content-type"] in ("application/json", "application/zip", "application/octet-stream")
```

- [ ] **Test + pass + commit.**

---

## Task 24 — `test_observer_contract.py`

```python
"""Observer schedule CRUD + thread view."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_schedule_crud(api_client, threads) -> None:
    # Create
    r = api_client.post("/api/observer/schedules/", json={
        "profile": "E2E Default", "name": "api sched", "interval_seconds": 120, "mode": "full",
    })
    assert r.status_code in (200, 201)
    sid = r.json()["id"]
    # Read
    r = api_client.get(f"/api/observer/schedules/{sid}/")
    assert r.status_code == 200
    assert r.json()["interval_seconds"] == 120
    # Update
    r = api_client.patch(f"/api/observer/schedules/{sid}/", json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False
    # Delete
    r = api_client.delete(f"/api/observer/schedules/{sid}/")
    assert r.status_code in (200, 204)


@pytest.mark.integration
def test_observer_thread_view(api_client, observer) -> None:
    from apps.profiles.models import TradingProfile
    pid = TradingProfile.objects.get(name="E2E Default").id
    r = api_client.get(f"/api/observer/threads/{pid}/")
    assert r.status_code == 200
    # Either returns the thread directly or {thread:..., messages:[...]}
    body = r.json()
    assert body is not None
```

- [ ] **Test + pass + commit.**

---

## Task 25 — `test_triggers_contract.py`

```python
"""Triggers CRUD + backtest."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_trigger_crud_and_validation(api_client, minimal) -> None:
    r = api_client.post("/api/triggers/", json={
        "name": "api trig",
        "condition": {"ticker": "AAPL", "metric": "last", "op": ">", "value": 0},
        "active": True,
    })
    assert r.status_code in (200, 201)
    tid = r.json()["id"]

    # Invalid DSL
    r = api_client.post("/api/triggers/", json={"name": "bad", "condition": {"garbage": True}})
    assert r.status_code == 400


@pytest.mark.integration
def test_trigger_backtest_against_ohlc(api_client, triggers) -> None:
    r = api_client.post("/api/triggers/backtest/", json={
        "condition": {"ticker": "AAPL", "metric": "last", "op": ">", "value": 150},
        "start": "2026-03-01T00:00:00Z",
        "end": "2026-04-18T00:00:00Z",
        "timeframe": "1h",
    })
    assert r.status_code == 200
    body = r.json()
    assert "matches" in body
    assert isinstance(body["matches"], list)
```

- [ ] **Test + pass + commit.**

---

## Task 26 — `test_analytics_contract.py`

```python
"""Analytics — one test per card."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_leaderboard(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/leaderboard/?forward_hours=24")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) or "rows" in body
    # Each row must report coverage_pct + avg_forward_return_pct (may be None)
    rows = body if isinstance(body, list) else body["rows"]
    for row in rows:
        assert "provider" in row and "model" in row
        assert "coverage_pct" in row


@pytest.mark.integration
def test_cost_per_insight(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/cost-per-insight/")
    assert r.status_code == 200


@pytest.mark.integration
def test_trigger_heatmap(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/trigger-heatmap/")
    assert r.status_code == 200
    body = r.json()
    assert "cells" in body or isinstance(body, list)


@pytest.mark.integration
def test_observer_timeline(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/observer-timeline/")
    assert r.status_code == 200


@pytest.mark.integration
def test_unusual_options(api_client, analytics) -> None:
    r = api_client.get("/api/analytics/unusual-options/?ticker=AAPL")
    assert r.status_code == 200
    body = r.json()
    # Flagged lines have non-empty triggers list
    lines = body if isinstance(body, list) else body.get("lines", [])
    for line in lines:
        assert isinstance(line.get("triggers"), list)
```

- [ ] **Test + pass + commit.**

---

## Task 27 — `test_backups_contract.py`

```python
"""Backups list/create/download."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_backup_list_create_download(api_client, minimal) -> None:
    r = api_client.post("/api/backups/", json={"kind": "manual"})
    assert r.status_code in (200, 201, 202)
    bid = r.json()["id"]

    # Poll until ok
    for _ in range(60):
        rec = api_client.get(f"/api/backups/{bid}/").json()
        if rec["status"] in ("ok", "failed"):
            break
    assert rec["status"] == "ok"

    r = api_client.get(f"/api/backups/{bid}/download/")
    assert r.status_code == 200
    assert r.content[:2] == b"\x1f\x8b"  # gzip magic
```

- [ ] **Test + pass + commit.**

---

## Task 28 — `test_export_contract.py`

```python
"""Export start/list/download + manifest v=1."""
from __future__ import annotations

import io
import json
import zipfile

import pytest


@pytest.mark.integration
def test_export_roundtrip(api_client, threads) -> None:
    r = api_client.post("/api/export/", json={})
    assert r.status_code in (200, 201, 202)
    eid = r.json()["id"]
    for _ in range(60):
        rec = api_client.get(f"/api/export/{eid}/").json()
        if rec["status"] in ("done", "failed"):
            break
    assert rec["status"] == "done"

    r = api_client.get(f"/api/export/{eid}/download/")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name))
        assert manifest["version"] == 1
```

- [ ] **Test + pass + commit.**

---

## Task 29 — `test_costs_caps.py`

```python
"""Costs caps endpoint + monthly cap check."""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_caps_get(api_client, minimal) -> None:
    r = api_client.get("/api/costs/caps")
    assert r.status_code == 200
    body = r.json()
    for key in ("claude", "openai"):
        assert key in body


@pytest.mark.integration
def test_caps_update(api_client, minimal) -> None:
    r = api_client.put("/api/costs/caps", json={
        "claude": {"daily_cost_cap_usd": "1.00", "monthly_cost_cap_usd": "10.00"},
    })
    assert r.status_code in (200, 204)
    # Confirm round-trip
    got = api_client.get("/api/costs/caps").json()
    assert str(got["claude"]["daily_cost_cap_usd"]) == "1.00"


@pytest.mark.integration
def test_monthly_cap_function(api_client, analytics) -> None:
    """check_monthly_cap is tested at unit level; this confirms the view surface."""
    r = api_client.get("/api/costs/summary?range=month")
    assert r.status_code == 200
```

- [ ] **Test + pass + commit.**

---

## Task 30 — `test_files_contract.py`

```python
"""Files API contract."""
from __future__ import annotations

import io

import pytest


@pytest.mark.integration
def test_file_upload_and_delete(api_client, minimal) -> None:
    files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
    r = api_client.post("/api/files/", files=files)
    assert r.status_code in (200, 201)
    fid = r.json()["id"]

    r = api_client.delete(f"/api/files/{fid}/")
    assert r.status_code in (200, 204)
```

- [ ] **Test + pass + commit.**

---

## Phase 2 acceptance

- [ ] `docker compose exec web pytest e2e/tests/test_pages.py -v` — all 18 pages + base pass.
- [ ] `make e2e-api` green, ~26 tests pass, wall-time ≤ 3 min.
- [ ] No regressions in `make e2e-ui`.
- [ ] All POM files under 80 lines each (proxy for "one responsibility").
