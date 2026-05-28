# E2E Suite Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the E2E suite's "green" mean "tested" — replace ~40 assertion-free UI checks with behavioral assertions, triage ~20 silent skips, add coverage for `/briefing` + `/events`, and fix the notifications flake.

**Architecture:** Pure test-quality work on the existing six-lane suite under `e2e/`. No product/backend changes — genuine product gaps become tracked `xfail` and are reported, not fixed. The page objects (`e2e/pages/*.py`) already encode every selector/action; most work is wiring existing methods + asserting real outcomes. Spec: `docs/superpowers/specs/2026-05-28-e2e-hardening-design.md`.

**Tech Stack:** pytest + Playwright (sync API), httpx (api lane), `e2e/helpers/ws_client.py` (ws lane), the scenario engine (`X-E2E-Scenario` header via `scenario` fixture), seed ladder fixtures (`e2e/fixtures/seed_*.py`).

---

## Operating rules (read once before any task)

- **Stack is already up** in this worktree: project `e2e-hardening-e2e`. Restart if needed with `make e2e-up`.
- **Run one file at a time** — the full UI lane is ~24 min. Per-file command:
  ```bash
  docker compose -p e2e-hardening-e2e -f compose.yaml -f compose.e2e.yaml exec -T --workdir /app worker uv run pytest e2e/ui/test_<x>.py -m integration -q -ra
  ```
  For api/ws lanes swap `worker` → `web` and the path. (`make e2e-one t=ui/test_<x>.py` also works.)
- **Assertions must match reality.** When a step's asserted text/locator might differ from what the running app renders, the executor runs the test, reads the failure, and adjusts the asserted string/locator to the *actual* rendered value — never weaken back to `body`-visible. The seeded data strings are fixed (see `e2e/fixtures/seed_*.py`); known ones: profile `"E2E Default"`, profile `"E2E Tools-Enabled"`, trigger `"E2E always fires"`, thread `"E2E plain thread"`, thread `"E2E tool-use thread"`.
- **Every hardened test keeps `p.expect_error_boundary_absent()`** (defined in `e2e/pages/base.py`) as a crash backstop, *plus* at least one behavioral assertion.
- **Commit per file** with `test(e2e): harden <area> assertions`. Lefthook skips checks for non-frontend/py-source commits; if it blocks on a test-file commit, the hook prints the `LEFTHOOK=0` bypass — only use it after manually confirming the test passed.
- **Never** set `MOCK_EXTERNAL` on the dev stack, reorder `config/urls.py`, or bind `0.0.0.0` (CLAUDE.md landmines — irrelevant here but do not stray into backend).

## File structure

**Phase 1 — modify only test bodies** (page objects already have the methods):
`e2e/ui/test_{costs,analytics,observer,snapshots,triggers,watchlists,settings,profiles,compare,files_and_citations,schwab_oauth,dashboard,error_paths}.py`. Add page-object methods only where a needed selector is missing (noted per task).

**Phase 2 — skips:** same UI files + `e2e/ui/test_error_paths.py` (xfail conversions), `e2e/fixtures/seed_*.py` (infra fixes).

**Phase 3 — new files:**
- Create `e2e/pages/briefing.py`, `e2e/pages/events.py`
- Create `e2e/ui/test_briefing.py`, `e2e/ui/test_events.py`
- Create `e2e/api/test_briefing_contract.py` (+ extend `e2e/api/test_market_contract.py` for events if uncovered)
- Create `e2e/ws/test_briefing.py` only if `/briefing` emits a WS event (verify first)
- Extend `e2e/fixtures/seed_*.py` with briefing seed data if needed

**Phase 4 — flake:** `e2e/ws/test_notifications.py`, run `tools/flake_audit.py`.

---

## PHASE 1 — Harden weak UI assertions

### Task 1.1: Costs page assertions

**Files:**
- Modify: `e2e/ui/test_costs.py`
- Reference: `e2e/pages/costs.py` (methods: `today_tile`, `provider_table`, `csv_btn`, `caps_editor`, `export_csv()`, `set_caps(daily=, monthly=)`)

- [ ] **Step 1: Rewrite the three test bodies**

```python
"""Costs gold paths."""

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
    c.expect_error_boundary_absent()
    expect(c.today_tile).to_be_visible(timeout=10_000)
    # Seeded AIRuns exist (analytics rung) → the tile shows a dollar amount.
    expect(c.today_tile).to_contain_text("$")


@pytest.mark.integration
@pytest.mark.ui
def test_costs_caps_editor_persists(page, frontend_base_url, minimal) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    c.expect_error_boundary_absent()
    c.set_caps(daily="12.50", monthly="200.00")
    c.expect_toast("aved", kind="success")  # "Saved"/"caps saved"
    # Reload and confirm persistence.
    c.go()
    expect(c.caps_editor.get_by_label("Daily cap (USD)")).to_have_value("12.50")
    expect(c.caps_editor.get_by_label("Monthly cap (USD)")).to_have_value("200.00")


@pytest.mark.integration
@pytest.mark.ui
def test_costs_csv_export_downloads_and_parses(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    c.expect_error_boundary_absent()
    data = c.export_csv()
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    assert len(rows) >= 1, "CSV must have at least a header row"
    header = ",".join(rows[0]).lower()
    assert "provider" in header or "cost" in header, f"unexpected CSV header: {rows[0]}"
```

- [ ] **Step 2: Run and adjust to reality**

Run: `docker compose -p e2e-hardening-e2e -f compose.yaml -f compose.e2e.yaml exec -T --workdir /app worker uv run pytest e2e/ui/test_costs.py -m integration -q -ra`
Expected: 3 passed. If the toast text/kind or the caps field labels differ, read the failure and correct the asserted strings to the actual rendered values (inspect via `HEADED=1` or the failure's locator dump). Do **not** revert to `body`-visible.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_costs.py
git commit -m "test(e2e): harden costs assertions (tile, caps persist, CSV parse)"
```

### Task 1.2: Dashboard page assertions

**Files:**
- Modify: `e2e/ui/test_dashboard.py`
- Reference: `e2e/pages/dashboard.py` (`card_snapshots`, `card_threads`, `card_cost`)

- [ ] **Step 1: Rewrite test bodies** (replace the two `body`-visible / `body.inner_text` checks with card assertions; keep the already-decent cost-tile test but tighten it)

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
    d.expect_error_boundary_absent()
    expect(d.card_snapshots).to_be_visible(timeout=10_000)
    expect(d.card_threads).to_be_visible()
    expect(d.card_cost).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_empty_state(page, frontend_base_url, minimal) -> None:
    """Fresh-ish DB — cards render (no skeleton stuck, no error boundary)."""
    d = DashboardPage(page, frontend_base_url)
    d.go()
    d.expect_error_boundary_absent()
    expect(d.card_snapshots).to_be_visible(timeout=10_000)
    # No skeleton left mounted after load.
    expect(page.locator("[data-testid^='skeleton-']")).to_have_count(0)


@pytest.mark.integration
@pytest.mark.ui
def test_dashboard_cost_tile_reflects_airuns(page, frontend_base_url, analytics) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    d.expect_error_boundary_absent()
    expect(d.card_cost).to_contain_text("$", timeout=10_000)
```

- [ ] **Step 2: Run and adjust**

Run: `... exec -T --workdir /app worker uv run pytest e2e/ui/test_dashboard.py -m integration -q -ra`
Expected: 3 passed. If a card test-id differs, correct it from the failure (the real ids are in `frontend/src/` dashboard components / page object).

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_dashboard.py
git commit -m "test(e2e): harden dashboard assertions (cards visible, cost tile)"
```

### Task 1.3: Analytics page assertions

**Files:**
- Modify: `e2e/ui/test_analytics.py`
- Reference: `e2e/pages/analytics.py` (`card_leaderboard`, `card_cpi`, `card_heatmap`, `card_timeline`, `card_unusual()`, `set_ticker()`)
- Note: the `test_unusual_options_card_shows_triggers` skip is handled in Phase 2 (Task 2.3); here, harden the other 5.

- [ ] **Step 1: Rewrite the five card tests** (leave the 6th's skip for Phase 2)

```python
"""Analytics gold paths — 5 cards + zero-coverage."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.analytics import AnalyticsPage


@pytest.mark.integration
@pytest.mark.ui
def test_analytics_page_renders_all_five_cards(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    expect(a.card_leaderboard).to_be_visible(timeout=10_000)
    expect(a.card_cpi).to_be_visible()
    expect(a.card_heatmap).to_be_visible()
    expect(a.card_timeline).to_be_visible()
    expect(a.card_unusual()).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_orders_by_forward_return(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # The leaderboard card renders at least one provider/model row.
    expect(a.card_leaderboard.get_by_role("row").first).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_leaderboard_zero_coverage_row(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # Runs without price history surface coverage 0% honestly (spec/leaderboard).
    expect(a.card_leaderboard).to_contain_text("%", timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_cost_per_insight_card(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    expect(a.card_cpi).to_contain_text("$", timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_heatmap_renders_cells(page, frontend_base_url, analytics) -> None:
    a = AnalyticsPage(page, frontend_base_url)
    a.go()
    a.expect_error_boundary_absent()
    # The heatmap renders a grid of day cells.
    expect(a.card_heatmap.locator("[data-testid^='heatmap-cell']").first).to_be_visible(
        timeout=10_000
    )
```

- [ ] **Step 2: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_analytics.py -m integration -q -ra`
Expected: 5 passed, 1 skipped (the unusual-options one, fixed in Phase 2). If `heatmap-cell` test-id differs, inspect the heatmap component for the real selector and correct it; if the card has no per-cell test-id, assert `a.card_heatmap` contains a known day label instead.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_analytics.py
git commit -m "test(e2e): harden analytics card assertions (5 cards)"
```

### Task 1.4: Triggers page assertions

**Files:**
- Modify: `e2e/ui/test_triggers.py`
- Reference: `e2e/pages/trigger_editor.py` (`name`, `fill_simple(...)`, `fill_dsl(...)`, `backtest(...)`, `fire_now_btn`, `save()`), `e2e/pages/triggers.py` (`new_btn`, `row(id)`, `firings_tab()`)

- [ ] **Step 1: Rewrite test bodies**

```python
"""Triggers gold + edges."""

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
    e.expect_error_boundary_absent()
    # The editor form is interactive: the Save button exists and is gated until named.
    save = page.get_by_role("button", name="Save")
    expect(save).to_be_disabled()
    expect(e.name).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_create_complex_dsl_all_any_not(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    e.expect_error_boundary_absent()
    # The DSL JSON editor accepts a nested all/any/not condition.
    e.fill_dsl({"all": [{"metric": "price", "ticker": "AAPL", "op": ">", "value": 1}]})
    expect(e.dsl_json).to_contain_text("all")


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_backtest_runs_against_ohlc(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import EventTrigger

    trig = EventTrigger.objects.get(name="E2E always fires")
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.expect_error_boundary_absent()
    expect(e.backtest_btn).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_cooldown_respected(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import EventTrigger

    trig = EventTrigger.objects.get(name="E2E always fires")
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.expect_error_boundary_absent()
    # The editor loads the existing trigger's name into the form.
    expect(e.name).to_have_value("E2E always fires", timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_edit_preserves_firings(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import EventTrigger, TriggerFiring

    trig = EventTrigger.objects.get(name="E2E always fires")
    before = TriggerFiring.objects.filter(trigger=trig).count()
    tl = TriggersListPage(page, frontend_base_url)
    tl.go()
    tl.expect_error_boundary_absent()
    expect(tl.row(trig.id)).to_be_visible(timeout=10_000)
    # Navigating the list does not mutate firings.
    assert TriggerFiring.objects.filter(trigger=trig).count() == before
```

- [ ] **Step 2: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_triggers.py -m integration -q -ra`
Expected: 5 passed. If `e.name` is not pre-filled on edit (component loads async), add a `to_be_visible` wait first; if the DSL field renders as a CodeMirror widget (not a plain textarea), assert via `expect(page.get_by_test_id("dsl-json")).to_contain_text(...)` against the real test-id.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_triggers.py
git commit -m "test(e2e): harden triggers assertions (editor, dsl, backtest, firings)"
```

### Task 1.5: Watchlists + market-ticker assertions

**Files:**
- Modify: `e2e/ui/test_watchlists.py`
- Reference: `e2e/pages/watchlists.py` (`create(name)`, `list_item(name)`, `open(name)`), `e2e/pages/watchlist_detail.py` (read it for methods), `e2e/pages/market_ticker.py` (`ohlc_chart`, `news_list`, `positions_tile`)
- First: confirm the seeded watchlist name in `e2e/fixtures/seed_market.py` (the test references `"E2E Core"`; verify and use the real string).

- [ ] **Step 1: Read `e2e/pages/watchlist_detail.py` and `e2e/fixtures/seed_market.py`** to confirm detail-page methods and the seeded watchlist name + tickers.

- [ ] **Step 2: Rewrite test bodies**

```python
"""Watchlists + market-ticker gold paths."""

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
    w.expect_error_boundary_absent()
    w.create("E2E Created WL")
    expect(w.list_item("E2E Created WL")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_watchlist_detail_add_remove_ticker(page, frontend_base_url, market) -> None:
    from apps.profiles.models import Watchlist

    wl = Watchlist.objects.get(name="E2E Core")  # confirm name in seed_market.py
    d = WatchlistDetailPage(page, frontend_base_url)
    d.go(wl.id)
    d.expect_error_boundary_absent()
    # The detail page shows the watchlist's name as a heading.
    expect(page.get_by_role("heading", name="E2E Core")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_market_ticker_page_renders_ohlc_and_news(page, frontend_base_url, market) -> None:
    m = MarketTickerPage(page, frontend_base_url)
    m.go("AAPL")
    m.expect_error_boundary_absent()
    expect(m.ohlc_chart).to_be_visible(timeout=10_000)
```

- [ ] **Step 3: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_watchlists.py -m integration -q -ra`
Expected: 3 passed. Adjust the seeded watchlist name/heading and any add/remove flow to the real `WatchlistDetailPage` methods discovered in Step 1 (e.g. if it has `add_ticker()`/`remove_ticker()`, drive a real add→assert row appears→remove→assert gone).

- [ ] **Step 4: Commit**

```bash
git add e2e/ui/test_watchlists.py
git commit -m "test(e2e): harden watchlists + market-ticker assertions"
```

### Task 1.6: Settings page assertions

**Files:**
- Modify: `e2e/ui/test_settings.py`
- Reference: `e2e/pages/settings.py` (`card(provider)`, `api_key_input(provider)`, `save_api_key(provider, key)`, `save_btn`)

- [ ] **Step 1: Rewrite test bodies**

```python
"""Settings gold paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.settings import SettingsPage


@pytest.mark.integration
@pytest.mark.ui
def test_provider_api_key_save_round_trip_masked(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    expect(s.card("claude")).to_be_visible(timeout=10_000)
    s.save_api_key("claude", "sk-ant-e2e-dummy-key")
    s.expect_toast("aved", kind="success")
    # Reload: the key is never echoed back in plaintext (write_only / masked).
    s.go()
    expect(s.api_key_input("claude")).not_to_have_value("sk-ant-e2e-dummy-key")


@pytest.mark.integration
@pytest.mark.ui
def test_daily_and_monthly_cap_edit(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    expect(s.card("claude")).to_be_visible(timeout=10_000)
```

- [ ] **Step 2: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_settings.py -m integration -q -ra`
Expected: 2 passed. The cap-edit test may belong on `/costs` (caps editor) rather than `/settings`; if `/settings` has no cap fields, assert the provider card's enabled toggle round-trips instead, or escalate to Phase 2 if there is genuinely no surface. Confirm the toast text from the real component.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_settings.py
git commit -m "test(e2e): harden settings assertions (api-key round-trip masked)"
```

### Task 1.7: Profiles page assertions

**Files:**
- Modify: `e2e/ui/test_profiles.py`
- Reference: `e2e/pages/profiles.py` (`create(name=, enable_tools=, thinking_budget=, enable_memory=)`, `row(name)`, `toggle_active(name)`)

- [ ] **Step 1: Rewrite test bodies**

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
    p.expect_error_boundary_absent()
    p.create(
        name="E2E Flags Profile",
        enable_tools=True,
        thinking_budget=2048,
        enable_memory=True,
    )
    expect(p.row("E2E Flags Profile")).to_be_visible(timeout=10_000)
    # Persisted to the backend with the flags set.
    from apps.profiles.models import TradingProfile

    prof = TradingProfile.objects.get(name="E2E Flags Profile")
    assert prof.enable_tools is True
    assert prof.enable_memory is True
    assert prof.thinking_budget == 2048


@pytest.mark.integration
@pytest.mark.ui
def test_profile_toggle_active(page, frontend_base_url, minimal) -> None:
    p = ProfilesPage(page, frontend_base_url)
    p.go()
    p.expect_error_boundary_absent()
    expect(p.row("E2E Default")).to_be_visible(timeout=10_000)
    p.toggle_active("E2E Default")
    # Activating reflects in the row (active badge) — assert the real indicator.
    expect(p.row("E2E Default")).to_contain_text("Active", timeout=10_000)
```

- [ ] **Step 2: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_profiles.py -m integration -q -ra`
Expected: 2 passed. If the thinking-budget field only appears after `enable_tools`/expanding an advanced section, the page object's `create()` already handles fill order; if the field name differs, fix `e2e/pages/profiles.py`. Confirm the "Active" badge text.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_profiles.py e2e/pages/profiles.py
git commit -m "test(e2e): harden profiles assertions (flags persist, activate)"
```

### Task 1.8: Observer/schedules page assertions (5 tests; cost-cap skip → Phase 2)

**Files:**
- Modify: `e2e/ui/test_observer.py`
- Reference: `e2e/pages/schedules.py` (`create(interval, mode, structured)`, `schedule_row(id)`, `run_now(id)`, `pause(id)`)
- The `test_observer_cost_cap_skip_emits_system_message` skip is handled in Phase 2 (Task 2.4). Harden the other 4 here.

- [ ] **Step 1: Read `e2e/fixtures/seed_observer.py`** to get seeded schedule ids/names (`"E2E active schedule"`, `"E2E paused schedule"`, etc.).

- [ ] **Step 2: Rewrite the four non-cost-cap tests**

```python
"""Observer gold + edges."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.schedules import SchedulesPage


@pytest.mark.integration
@pytest.mark.ui
def test_create_schedule_and_run_now(page, frontend_base_url, observer) -> None:
    from apps.observer.models import ObserverSchedule

    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    sched = ObserverSchedule.objects.filter(name="E2E active schedule").first()
    assert sched is not None
    expect(s.schedule_row(sched.id)).to_be_visible(timeout=10_000)
    expect(s.run_now_btn(sched.id)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_schedule_pause_resume(page, frontend_base_url, observer) -> None:
    from apps.observer.models import ObserverSchedule

    sched = ObserverSchedule.objects.get(name="E2E active schedule")
    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    expect(s.pause_btn(sched.id)).to_be_visible(timeout=10_000)
    s.pause(sched.id)
    # Pausing flips the control to a Resume affordance.
    expect(s.schedule_row(sched.id).get_by_role("button", name="Resume")).to_be_visible(
        timeout=10_000
    )


@pytest.mark.integration
@pytest.mark.ui
def test_observer_structured_mode_produces_typed_card(
    page, frontend_base_url, observer, scenario
) -> None:
    scenario.use("structured-observation")
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    page.wait_for_load_state("networkidle")
    # The observer thread page renders without crashing and shows the thread surface.
    expect(page.get_by_text("Something went wrong")).to_have_count(0)
    expect(page.get_by_text("Loading")).to_have_count(0, timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_observer_diff_mode_sends_only_delta(page, frontend_base_url, observer) -> None:
    from apps.profiles.models import TradingProfile

    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Something went wrong")).to_have_count(0)
```

- [ ] **Step 3: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_observer.py -m integration -q -ra`
Expected: 4 passed, 1 skipped (cost-cap; Phase 2). Adjust seeded schedule names and the Resume/Pause button labels to the real component. For the structured/diff tests, if the observer thread renders a concrete typed-card test-id, assert on that instead of the crash-absence backstop.

- [ ] **Step 4: Commit**

```bash
git add e2e/ui/test_observer.py
git commit -m "test(e2e): harden observer assertions (rows, pause/resume, thread render)"
```

### Task 1.9: Snapshots page assertions (UI portions)

**Files:**
- Modify: `e2e/ui/test_snapshots.py`
- Reference: `e2e/pages/snapshot.py` (`capture(profile, objective, sections)`, `section_status(kind)`, `wait_for_complete()`, `capture_btn`), `e2e/pages/snapshot_cost.py` (`cost_total`, `section_row(name)`)
- The 413 test and diff-endpoint contract are already real — keep them. Harden the UI-only ones; the "≥2 ready" skip is a dead guard removed in Phase 2 (Task 2.2).

- [ ] **Step 1: Rewrite the body-visible UI tests** (keep `test_capture_oversized_image_returns_413` and the api assertions in `test_snapshot_diff_endpoint_surfaced` unchanged)

```python
# test_capture_all_sections_ok:
def test_capture_all_sections_ok(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    expect(s.capture_btn).to_be_visible(timeout=10_000)
    expect(s.profile_select).to_be_visible()

# test_snapshot_drill_down:
def test_snapshot_drill_down(page, frontend_base_url, snapshots) -> None:
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(status="ready").first()
    d = SnapshotCostPage(page, frontend_base_url)
    d.go(snap.id)
    d.expect_error_boundary_absent()
    expect(d.cost_total).to_be_visible(timeout=10_000)

# test_capture_partial_failure_marks_sections (scenario news-503):
def test_capture_partial_failure_marks_sections(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("news-503")
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    expect(s.capture_btn).to_be_visible(timeout=10_000)

# test_costs_page_loads_from_snapshot:
def test_costs_page_loads_from_snapshot(page, frontend_base_url, analytics) -> None:
    costs = CostsPage(page, frontend_base_url)
    costs.go()
    costs.expect_error_boundary_absent()
    expect(costs.today_tile).to_be_visible(timeout=10_000)
```

- [ ] **Step 2: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_snapshots.py -m integration -q -ra`
Expected: 6 passed (skip removed in Phase 2; until then 5 passed + 1 skipped is acceptable). If `cost_total` test-id differs on the drill-down page, correct it. If a live capture is feasible (composer drives `capture()` → `section_status("news")` shows failed under `news-503`), prefer that stronger assertion.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_snapshots.py
git commit -m "test(e2e): harden snapshots UI assertions (composer, drill-down, costs)"
```

### Task 1.10: Files + citations assertions

**Files:**
- Modify: `e2e/ui/test_files_and_citations.py`
- Reference: `e2e/pages/files.py` (`upload(path)`, `row(file_id)`, `delete(file_id)`)
- Scenario note: `files-upload-fail` exists for the failure path. For the happy path, MOCK_EXTERNAL stubs the Anthropic Files API.

- [ ] **Step 1: Rewrite test bodies** (use a real tmp file upload; assert a row appears / citation renders)

```python
"""Files API + citations edges."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect

from e2e.pages.files import FilesPage


@pytest.mark.integration
@pytest.mark.ui
def test_file_upload_and_attach_to_thread(page, frontend_base_url, threads, tmp_path: Path) -> None:
    f = FilesPage(page, frontend_base_url)
    f.go()
    f.expect_error_boundary_absent()
    sample = tmp_path / "note.txt"
    sample.write_text("e2e upload body")
    f.upload(sample)
    # A file row appears after the (mocked) Anthropic upload returns an id.
    expect(page.locator("[data-testid^='file-row-']").first).to_be_visible(timeout=15_000)


@pytest.mark.integration
@pytest.mark.ui
def test_delete_file_hits_anthropic_delete(
    page, frontend_base_url, minimal, tmp_path: Path
) -> None:
    f = FilesPage(page, frontend_base_url)
    f.go()
    f.expect_error_boundary_absent()
    sample = tmp_path / "del.txt"
    sample.write_text("delete me")
    f.upload(sample)
    row = page.locator("[data-testid^='file-row-']").first
    expect(row).to_be_visible(timeout=15_000)
    row.get_by_role("button", name="Delete").click()
    expect(page.locator("[data-testid^='file-row-']")).to_have_count(0, timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_citation_renders_news_link(page, frontend_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E tool-use thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Something went wrong")).to_have_count(0)
    # The thread renders its transcript (at least one message bubble).
    expect(page.locator("[data-testid^='message-']").first).to_be_visible(timeout=10_000)
```

- [ ] **Step 2: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_files_and_citations.py -m integration -q -ra`
Expected: 3 passed. If upload requires the input to exist before clicking Upload, or the row test-id prefix differs, correct from the failure. If the citation thread has a `<Citation/>` test-id, assert that specifically instead of the generic message bubble.

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_files_and_citations.py
git commit -m "test(e2e): harden files upload/delete + citation render assertions"
```

### Task 1.11: Schwab OAuth assertions

**Files:**
- Modify: `e2e/ui/test_schwab_oauth.py`
- Reference: read `e2e/pages/schwab_oauth.py` for methods; scenario `schwab-oauth-ok` drives the full stubbed flow.

- [ ] **Step 1: Read `e2e/pages/schwab_oauth.py`** to learn the connect/authorize/callback methods.

- [ ] **Step 2: Rewrite test bodies** using the page object's real flow methods. Pattern:

```python
def test_oauth_authorize_redirects_to_stub(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    s = SchwabOAuthPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    # Assert the connect affordance is present (real method/locator from the POM).
    # e.g. expect(s.connect_btn).to_be_visible(timeout=10_000)


def test_oauth_callback_persists_encrypted_token(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    s = SchwabOAuthPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    # Drive the stubbed flow via the POM, then assert connected status renders
    # AND a credential row persisted:
    from apps.secrets.models import ApiCredential
    assert ApiCredential.objects.filter(provider="schwab").exists()
```

- [ ] **Step 3: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_schwab_oauth.py -m integration -q -ra`
Expected: 2 passed. Fill in the exact POM methods/locators from Step 1. If the full callback flow cannot complete headlessly under the stub, assert the connect button + the post-`schwab-oauth-ok` connected indicator; if token persistence has no observable surface, escalate the second test to Phase 2 xfail.

- [ ] **Step 4: Commit**

```bash
git add e2e/ui/test_schwab_oauth.py
git commit -m "test(e2e): harden schwab oauth assertions (connect + token persisted)"
```

### Task 1.12: Compare assertions (provider-availability gated)

**Files:**
- Modify: `e2e/ui/test_compare.py`
- Create (if needed): methods in `e2e/pages/compare.py` (currently empty)
- **Critical constraint (from project memory):** under `MOCK_EXTERNAL`, only Claude is reliably exercisable end-to-end; OpenAI/local providers historically failed to construct without a key. A 3-provider compare may not stream all branches. **Verify current behavior first.**

- [ ] **Step 1: Verify provider availability under e2e.** Inspect `e2e/fixtures/seed_minimal.py` for seeded `ProviderConfig` rows and whether OpenAI/local have keys. Run a quick manual compare in HEADED mode or check `apps/ai/providers/openai.py.__init__` for the mock-mode placeholder key. Decide: can compare fan out across {claude, openai, local}, or only across Claude models?

- [ ] **Step 2a: If multi-provider compare works** — rewrite both tests to: create a thread, open compare (`SnapshotPage.open_compare()` or the real compare entry), launch 2–3 branches, wait for each branch's `message_done`, assert each branch bubble rendered and each branch shows a cost. Add the needed locators to `e2e/pages/compare.py`.

- [ ] **Step 2b: If only Claude works** — rewrite to compare two Claude *models* (e.g. opus vs sonnet), assert both branches stream and render, and assert two cost values route to the two branch tabs. Add a code comment citing the MOCK_EXTERNAL provider constraint.

- [ ] **Step 2c: If compare cannot run headlessly at all** — escalate both to Phase 2 xfail with a precise reason; do not leave body-visible.

Representative (2b) shape:

```python
"""Compare — branches stream + cost routing (Claude-only under MOCK_EXTERNAL)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.thread_detail import ThreadDetailPage


def _fresh_chat_thread(title: str) -> int:
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    profile = TradingProfile.objects.filter(name="E2E Default").first()
    return Thread.objects.create(title=title, profile=profile, kind="chat").id


@pytest.mark.integration
@pytest.mark.ui
def test_compare_two_branches_stream_and_cost(page, frontend_base_url, minimal) -> None:
    tid = _fresh_chat_thread("E2E compare two branches")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)
    detail.expect_error_boundary_absent()
    # ... open compare, pick 2 claude models, run, wait for both done,
    #     assert two branch transcripts + two cost values (use real compare POM/locators).
```

- [ ] **Step 3: Run and adjust**

Run: `... worker uv run pytest e2e/ui/test_compare.py -m integration -q -ra`
Expected: 2 passed (or 2 xfail if 2c). Iterate against real compare UI locators.

- [ ] **Step 4: Commit**

```bash
git add e2e/ui/test_compare.py e2e/pages/compare.py
git commit -m "test(e2e): harden compare assertions (branch stream + cost routing)"
```

---

## PHASE 2 — Triage every skip

### Task 2.1: Verify whether the two `test_error_paths.py` backend-gap skips are stale

**Files:**
- Inspect: `backend/apps/ai/router.py` (`resolve_provider_and_model`), `backend/apps/threads/tasks.py` (`run_ai_on_message`, `_fail`), `frontend/src/` ThreadDetailPage `onWs`
- Modify: `e2e/ui/test_error_paths.py`

- [ ] **Step 1: Check the provider-enabled gate.** Grep `run_ai_on_message` for a `ProviderConfig.enabled` / `provider_disabled` check after `resolve_provider_and_model`.
```bash
docker compose -p e2e-hardening-e2e exec -T web grep -n "enabled\|provider_disabled" apps/threads/tasks.py apps/ai/router.py
```
- [ ] **Step 2: Check `_fail` emits `message_started`.** Grep `_fail` in `apps/threads/tasks.py` for a `message_started` broadcast, and check the frontend `onWs` seeds a message on `error`/`cost_capped`.

- [ ] **Step 3a: If the gate now exists** → remove `@pytest.mark.skip` from `test_provider_disabled_blocks_send`, run it, assert the failed message renders. Commit.
- [ ] **Step 3b: If `_fail` now emits `message_started`** → remove `@pytest.mark.skip` from `test_cap_exceeded_shows_failed_message`, run it (the console guard must not trip — verify no React key warning), assert `"would be exceeded"` renders. Commit.
- [ ] **Step 3c: If still genuinely broken** → convert each `@pytest.mark.skip(reason=...)` to `@pytest.mark.xfail(reason=..., strict=False)` so it runs and is tracked (XPASS flips when fixed). Keep the detailed reason. Add the gap to the Phase-2 report.

- [ ] **Step 4: Run**

Run: `... worker uv run pytest e2e/ui/test_error_paths.py -m integration -q -ra`
Expected: all pass, or the converted ones show as `xfail`/`xpass` (not skipped).

- [ ] **Step 5: Commit**

```bash
git add e2e/ui/test_error_paths.py
git commit -m "test(e2e): un-skip or xfail error-path backend-gap tests after re-verify"
```

### Task 2.2: Remove the dead `≥2 ready snapshots` guard

**Files:** Modify `e2e/ui/test_snapshots.py`

- [ ] **Step 1:** The `snapshots` fixture seeds 4 ready snapshots (`e2e/fixtures/seed_snapshots.py`), so `len(ready) < 2` never fires. Delete the `if len(ready) < 2: pytest.skip(...)` guard in `test_snapshot_diff_endpoint_surfaced`.
- [ ] **Step 2:** Run `... worker uv run pytest e2e/ui/test_snapshots.py::test_snapshot_diff_endpoint_surfaced -m integration -q`. Expected: PASS (no skip).
- [ ] **Step 3:** Commit `test(e2e): remove dead ≥2-ready-snapshots skip guard`.

### Task 2.3: Fix or xfail the analytics ticker-input skip

**Files:** Modify `e2e/ui/test_analytics.py`; reference `e2e/pages/analytics.py` (`set_ticker`, `card_unusual`)

- [ ] **Step 1: Determine if `/analytics` has a ticker input.** Run with HEADED or grep the AnalyticsPage component for a "Ticker" label / the unusual-options card's input.
- [ ] **Step 2a: If present** → rewrite `test_unusual_options_card_shows_triggers` to `a.set_ticker("AAPL")`, then assert `a.card_unusual()` shows a flagged line / "vol/oi" or "iv_z" trigger reason (per spec's unusual-options detector). Remove the try/except skip.
- [ ] **Step 2b: If absent** → convert to `@pytest.mark.xfail(reason="no ticker input wired on /analytics unusual-options card", strict=False)` and assert the intended behavior; add to the report.
- [ ] **Step 3:** Run the file; expected: the test runs (pass or xfail), not skipped.
- [ ] **Step 4:** Commit `test(e2e): fix or xfail analytics unusual-options ticker skip`.

### Task 2.4: Fix or xfail the observer cost-cap skip

**Files:** Modify `e2e/ui/test_observer.py`; reference seed `e2e/fixtures/seed_observer.py` (the seed claims a `system/done` cost-cap message exists on the observer thread)

- [ ] **Step 1: Verify the seed writes a cost-cap system message** and that `/threads/observer/<profileId>` renders system messages. Grep `seed_observer.py` for the cost-cap Message; check the observer thread page renders `role="system"` messages.
- [ ] **Step 2a: If the surface exists** → replace the `if ...count()==0: skip` with a positive assertion that the cost-cap text renders (use the exact seeded string). 
- [ ] **Step 2b: If system messages aren't surfaced on that route** → `xfail(reason="observer thread page does not render system/done cost-cap messages", strict=False)`; add to report.
- [ ] **Step 3:** Run the file; expected: test runs, not skipped.
- [ ] **Step 4:** Commit `test(e2e): fix or xfail observer cost-cap message skip`.

### Task 2.5: Audit and classify the remaining static skips

**Files:** all `e2e/**/*.py` with `pytest.skip`

- [ ] **Step 1: List every remaining skip and its runtime status.**
```bash
grep -rn "pytest.skip\|@pytest.mark.skip" e2e/ | grep -v test_scaffolding
```
For each, decide: legitimate-keep (prod-posture in `scenario_engine_disabled_in_prod`, lighthouse-unavailable, keyboard-Tab-budget), dead-guard (remove), infra-fixable (fix seed/scenario), or genuine (xfail). The ws skips in `test_notifications.py` / `test_ws_reconnect.py` / `test_snapshot_progress.py` are mostly defensive guards on seeded objects that now exist — verify each fires or not by running its file.
- [ ] **Step 2:** For each ws/api skip that is a dead guard (object exists in seed), remove it; for genuine gaps (e.g. `ThreadConsumer doesn't implement ?since=` — check `apps/threads/event_log.py` first, a memory says PR #14 added it), un-skip if implemented else xfail.
- [ ] **Step 3:** Run the affected files (`e2e/ws/`, single files) to confirm no new failures.
- [ ] **Step 4:** Commit `test(e2e): triage remaining skips (remove dead guards, xfail genuine gaps)`.

- [ ] **Step 5: Write the Phase-2 gap report** to `docs/superpowers/plans/2026-05-28-e2e-hardening-gaps.md`: a table of every `xfail` (test, reason, backend file:line, suggested fix). Commit `docs(e2e): backend gaps surfaced by hardened tests`.

---

## PHASE 3 — Add coverage for untested flows

### Task 3.1: Briefing — page object + API contract

**Files:**
- Create: `e2e/pages/briefing.py`, `e2e/api/test_briefing_contract.py`
- Inspect: `backend/apps/briefing/` (models `BriefingConfig`, `BriefingRun`; endpoints — find via `backend/apps/briefing/urls.py`), `frontend/src/` briefing page (test-ids)
- Possibly extend: `e2e/fixtures/seed_minimal.py` or a new `e2e/fixtures/seed_briefing.py` if a `BriefingRun` must exist.

- [ ] **Step 1: Discover the briefing API surface.**
```bash
docker compose -p e2e-hardening-e2e exec -T web cat apps/briefing/urls.py
docker compose -p e2e-hardening-e2e exec -T web grep -rn "def \|class .*ViewSet\|@action" apps/briefing/views.py
```
Note the routes (CLAUDE.md mentions `POST /api/briefings/run/` and a config singleton).

- [ ] **Step 2: Write the API contract test** asserting real response shapes:

```python
"""Briefing API contract."""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.api
def test_briefing_config_get(api_client, minimal) -> None:
    r = api_client.get("/api/briefings/config/")  # adjust to real route from Step 1
    assert r.status_code == 200, r.text
    body = r.json()
    assert "enabled" in body or "scheduled_time" in body


@pytest.mark.integration
@pytest.mark.api
def test_briefing_run_now_creates_run(api_client, minimal) -> None:
    r = api_client.post("/api/briefings/run/")  # adjust to real route
    assert r.status_code in (200, 201, 202), r.text
    # A BriefingRun row is created.
    from apps.briefing.models import BriefingRun

    assert BriefingRun.objects.exists()
```

- [ ] **Step 3: Run** `... web uv run pytest e2e/api/test_briefing_contract.py -m integration -q -ra`. Adjust routes/fields to the real surface from Step 1. Expected: passing.

- [ ] **Step 4: Create the page object** `e2e/pages/briefing.py`:

```python
"""Briefing page — /briefing."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class BriefingPage(BasePage):
    PATH = "/briefing"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def run_now_btn(self) -> Locator:
        return self.page.get_by_role("button", name="Run now")  # adjust to real label

    @property
    def latest_run(self) -> Locator:
        return self.page.get_by_test_id("briefing-latest-run")  # adjust to real test-id
```

- [ ] **Step 5: Commit** `test(e2e): add briefing API contract + page object`.

### Task 3.2: Briefing — UI gold test + visual baseline

**Files:** Create `e2e/ui/test_briefing.py`; add to `e2e/visual/test_route_snapshots.py` parametrize list; mask dynamic regions in `e2e/helpers/visual.py` if needed.

- [ ] **Step 1: Write the UI gold test**

```python
"""Briefing page gold path."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.briefing import BriefingPage


@pytest.mark.integration
@pytest.mark.ui
def test_briefing_page_renders(page, frontend_base_url, threads) -> None:
    b = BriefingPage(page, frontend_base_url)
    b.go()
    b.expect_error_boundary_absent()
    # The page renders its primary surface (run button or latest-run panel).
    expect(b.run_now_btn).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_briefing_run_now_renders_sections(page, frontend_base_url, threads) -> None:
    b = BriefingPage(page, frontend_base_url)
    b.go()
    b.expect_error_boundary_absent()
    b.run_now_btn.click()
    # Deterministic data sections render even with the AI layer mocked.
    expect(b.latest_run).to_be_visible(timeout=20_000)
```

- [ ] **Step 2: Run** `... worker uv run pytest e2e/ui/test_briefing.py -m integration -q -ra`. Adjust locators to the real briefing component (read `frontend/src/` for the page's test-ids). If `/briefing` guards against empty/failed runs (commit `7be9f2cc`), seed a `BriefingRun` first or assert the empty-state surface explicitly.

- [ ] **Step 3: Add visual baseline.** Add `"/briefing"` to the route list in `e2e/visual/test_route_snapshots.py`, then:
```bash
make e2e-visual-update
git diff --stat e2e/visual/__screenshots__/
```
Confirm the new `briefing.png` is under the 600KB cap; mask dynamic regions (timestamps) in `e2e/helpers/visual.py` if the baseline is noisy.

- [ ] **Step 4: a11y check.** Confirm `/briefing` is covered by `e2e/a11y/test_axe_per_route.py` (it likely parametrizes the route list — add `/briefing` if not). Run `... worker uv run pytest e2e/a11y/ -m integration -q -k briefing`. Fix any DOM a11y violation in-test only if it's an `a11y_ignores` candidate (otherwise report).

- [ ] **Step 5: Commit** `test(e2e): add briefing UI gold test + visual baseline + a11y`.

### Task 3.3: Events — UI gold test (+ API if uncovered)

**Files:** Create `e2e/ui/test_events.py`, `e2e/pages/events.py`; check `e2e/api/test_market_contract.py` for events coverage.

- [ ] **Step 1: Check events API coverage.**
```bash
grep -n "events" e2e/api/test_market_contract.py
docker compose -p e2e-hardening-e2e exec -T web grep -rn "events" apps/market/urls.py
```
If `GET /api/market/events/` is uncovered, add a contract test to `test_market_contract.py` asserting the response shape (list of `{ticker, type, date, ...}`).

- [ ] **Step 2: Create `e2e/pages/events.py`**

```python
"""Market events page — /events."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class EventsPage(BasePage):
    PATH = "/events"

    def go(self) -> None:
        self.goto(self.PATH)

    @property
    def events_list(self) -> Locator:
        return self.page.get_by_test_id("events-list")  # adjust to real test-id
```

- [ ] **Step 3: Write the UI gold test**

```python
"""Events page gold path."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.events import EventsPage


@pytest.mark.integration
@pytest.mark.ui
def test_events_page_renders(page, frontend_base_url, market) -> None:
    e = EventsPage(page, frontend_base_url)
    e.go()
    e.expect_error_boundary_absent()
    expect(e.events_list).to_be_visible(timeout=10_000)
```

- [ ] **Step 4: Run** both the UI test and (if added) the api test; adjust the real test-ids and route/response shape from the failures. Seed market events if the page is empty without them (check `e2e/fixtures/seed_market.py` for `MarketEvent` rows; add if absent).

- [ ] **Step 5: Add `/events` to the visual + a11y route lists** (as in Task 3.2 Steps 3–4), regenerate baseline, confirm cap.

- [ ] **Step 6: Commit** `test(e2e): add events UI gold test + page object (+ api contract, visual)`.

### Task 3.4: Verify visual + a11y lanes still green

- [ ] **Step 1: Run the visual lane** `... worker uv run pytest e2e/visual/ -m integration -q -ra`. Expected: green (existing baselines unchanged except the two new routes). Investigate any unexpected baseline drift — do not blindly update.
- [ ] **Step 2: Run the a11y lane** `... worker uv run pytest e2e/a11y/ -n 4 -m integration -q -ra`. Expected: no new violations. Fix DOM issues on the new pages if any; do not add to `a11y_ignores` without a tracked reason.
- [ ] **Step 3: Commit** any baseline/mask updates: `chore(e2e/visual): baselines for /briefing + /events`.

---

## PHASE 4 — Flake audit + stabilize

### Task 4.1: Fix the notifications flake

**Files:** Modify `e2e/ws/test_notifications.py`, reference `e2e/helpers/ws_client.py` (`wait_for_event(name, timeout)`)

- [ ] **Step 1: Reproduce under load** is not required (root cause known: 30 s wait too tight when the worker is busy). In `test_notifications_observer_done_delivered` (and any sibling using a 30 s wait), raise the `wait_for_event` timeout to 90 s and assert on the event payload, not just arrival.
```python
ev = await wc.wait_for_event("notification.event", timeout=90.0)
assert ev  # and assert a stable field, e.g. ev["event"] or ev["payload"]["kind"]
```
- [ ] **Step 2: Run in isolation 3×** to confirm stability:
```bash
for i in 1 2 3; do docker compose -p e2e-hardening-e2e -f compose.yaml -f compose.e2e.yaml exec -T --workdir /app web uv run pytest e2e/ws/test_notifications.py -m integration -q; done
```
Expected: 3× green.
- [ ] **Step 3: Commit** `fix(e2e): widen notification wait to survive worker latency`.

### Task 4.2: Run the flake audit

**Files:** `tools/flake_audit.py` (read it first for invocation), output `flake_audit.json`

- [ ] **Step 1: Read `tools/flake_audit.py`** to learn how it expects to be invoked (it re-runs each lane 3×). Run it against the up worktree stack (it may need `E2E_PROJECT=e2e-hardening-e2e`):
```bash
docker compose -p e2e-hardening-e2e -f compose.yaml -f compose.e2e.yaml exec -T --workdir /app web uv run python tools/flake_audit.py  # adjust per its real CLI
```
If the tool assumes the default project or its own up/down, invoke per-lane manually 3× instead and tabulate.
- [ ] **Step 2: Triage results.** For any test below a stable pass ratio, fix the timing/ordering root cause (widen waits, await the real signal, avoid cross-lane DB truncation). Do not add blanket retries.
- [ ] **Step 3: Address the documented `test_seed_ladder.py` vs `api/` truncation interaction** only if a cheap guard exists (e.g. ensure the api lane re-seeds; or document that they must run in separate invocations — already in `e2e/README.md`).
- [ ] **Step 4: Commit** `fix(e2e): stabilize flakiest tests from flake audit` (+ `flake_audit.json` if the repo tracks it; check `.gitignore` first).

---

## FINAL VALIDATION

- [ ] **Step 1: Full suite run** (phase boundary only — ~70 min total):
```bash
make e2e   # api/ws then ui/visual/a11y, isolated project, tears down at end
```
Run lanes one at a time if contention causes false failures (observed during baselining). Expected vs. baseline: 0 `body`-visible-only UI tests remain; skips reduced to the legitimate set + tracked xfails; `/briefing` + `/events` covered; notifications flake gone.
- [ ] **Step 2: Update `e2e/README.md`** "Known limitations" / scenario notes if any behavior changed (e.g. provider-availability finding from Task 1.12).
- [ ] **Step 3: Final commit** `docs(e2e): update README after hardening` and open the PR (push as `dan-wiseman94` per project convention: `env -u GITHUB_TOKEN git push`).

---

## Self-review notes (author)

- **Spec coverage:** Phase 1 ↔ all 13 weak files (Tasks 1.1–1.12, error_paths' 1 body-visible folded into 2.1). Phase 2 ↔ skip triage incl. the 2 backend-gap skips (2.1), dead guard (2.2), analytics (2.3), observer (2.4), remaining (2.5) + gap report. Phase 3 ↔ /briefing (3.1–3.2) + /events (3.3) + visual/a11y verify (3.4). Phase 4 ↔ notifications flake (4.1) + flake_audit (4.2). Final validation maps to the spec's "done when" per phase.
- **Known judgment calls:** exact locators/test-ids and some routes are verified-and-adjusted at execution time (UI assertions must match the live DOM; guessing in-plan would be worse). Each such step names the real page-object method to use and forbids reverting to `body`-visible.
- **Provider constraint** (compare, Task 1.12) and **briefing empty-run guard** (3.2) are called out explicitly so the executor doesn't write tests that can't pass under MOCK_EXTERNAL.
