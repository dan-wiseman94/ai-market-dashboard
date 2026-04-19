# Comprehensive E2E Test Suite — Design

**Date:** 2026-04-18
**Status:** Draft for user review
**Scope:** Replace the current 6-journey happy-path suite with a six-lane comprehensive suite covering UI, API contract, WebSocket, visual regression, accessibility, and performance across all routes and M1–M12 features.

---

## 1. Goals & non-goals

### Goals
- One UI journey per top-level route, covering both gold paths and key error paths.
- Contract tests for every DRF ViewSet / endpoint.
- Event-ordering assertions for every Channels WebSocket group.
- Page-level visual regression on every route, page-level.
- A11y scans (axe, critical+serious) on every route + one keyboard-only journey.
- Lighthouse performance budgets on five representative routes.
- Deterministic, hermetic execution via `MOCK_EXTERNAL=true` + a scenario engine.
- `make e2e` green within 30 min on a fresh clone; `<1%` flake rate.

### Non-goals (v1)
- Dark-mode visual snapshots.
- Cross-browser matrix (chromium-only).
- Real-provider canary lane (deferred; revisit after v1 stabilizes).
- Bundle-size / RUM / web-vitals-in-prod budgets.
- Storybook + Chromatic component-level visual diffs.
- Mutation / property-based testing.

### Success criteria
- `make e2e` passes on a fresh clone within 30 min.
- CI `e2e` workflow green on main for 14 consecutive days before declaring "done."
- Flake rate <1% (measured by nightly 3× re-runs against main).
- Every top-level route has ≥1 UI test, ≥1 a11y scan, ≥1 visual baseline.
- Every backend DRF ViewSet has ≥1 API contract test.
- Every WS group has ≥1 event-ordering assertion.

---

## 2. Architecture

Six independent lanes, each with its own conftest and selection filter, sharing a seed ladder and scenario engine.

```
e2e/
  conftest.py              — session fixtures: stack health, playwright, scenario client, seed ladder
  fixtures/                — seed ladder (7 rungs, §3)
  mocks/                   — scenario engine dispatch layer (§7)
    client.py              — ScenarioClient (header injection for page + api)
  pages/                   — POM (~18 page objects, fleshed out — §6)
  helpers/
    ws_client.py           — websockets wrapper with event collector + retry
    api_client.py          — httpx session with auth + X-E2E-Scenario injection
    axe_runner.py          — axe-playwright-python wrapper, filtered to critical+serious
    lighthouse_runner.py   — shells out to `lighthouse` CLI, parses JSON
    visual.py              — wait_for_stable(), disable_animations(), mask helpers
  ui/                      — ~50 Playwright journeys (§4)
  api/                     — ~25 httpx contracts (§5)
  ws/                      — ~10 Channels event assertions (§5)
  visual/                  — ~20 page-level baselines
    test_route_snapshots.py
    __screenshots__/       — committed PNG baselines, ≤500KB each
  a11y/                    — ~15 axe per-route + keyboard-only journey
    test_axe_per_route.py
    test_keyboard_only.py
    a11y_ignores.py
  perf/                    — 5 Lighthouse routes
    test_lighthouse.py
    budgets.json
```

**Lane driver summary:**

| Lane    | Driver                                  | Wall clock | Parallelism              |
|---------|-----------------------------------------|------------|---------------------------|
| ui      | Playwright sync + pytest-xdist          | ~10 min    | `-n 4 --dist=loadscope`  |
| api     | httpx                                   | ~2 min     | `-n 4`                    |
| ws      | `websockets` library                    | ~3 min     | `-n 2` (Channels group races above) |
| visual  | Playwright `toHaveScreenshot()`         | ~5 min     | `-n 2`                    |
| a11y    | `axe-playwright-python`                 | ~3 min     | `-n 4`                    |
| perf    | `lighthouse` npm CLI via `frontend` container | ~5 min | serial (deterministic)    |

All lanes run under `docker compose -f compose.yaml -f compose.e2e.yaml` which sets `MOCK_EXTERNAL=true`, `OBSERVER_TEST_MIN_INTERVAL_SECONDS=1`, `TRIGGER_TEST_COOLDOWN_SECONDS=1`, and (new) `TRIGGER_EVAL_INTERVAL_SECONDS=1`.

---

## 3. Seed ladder

Seven rungs under `e2e/fixtures/`. Each is an idempotent function; each calls its prerequisite. Tests declare the highest rung they need via pytest fixture; rungs below run automatically.

| Rung | Function         | Creates                                                                                                                                                                                                                       | Depends on |
|------|------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------|
| 1    | `seed_minimal()` | 3 `ProviderConfig` (claude, openai, local); 2 `TradingProfile` — `E2E Default`, `E2E Tools-Enabled` (with `enable_tools/thinking/memory=True`, `thinking_budget=2048`).                                                          | —          |
| 2    | `seed_market()`  | 3 watchlists (`E2E Core`, `E2E Tech`, `E2E Empty`); 8 tickers; 30 days of `OHLCBar` for AAPL/MSFT/SPY/VIX (1h timeframe); 5 `Position` rows; 10 `NewsItem`; 14 days of `OptionChainSnapshot` for AAPL with ≥1 line that trips unusual-options (`volume/oi=4.0`, `iv_z=2.1`). | minimal    |
| 3    | `seed_snapshots()` | 3 `Snapshot` (status=ready, all 7 sections populated + `payload_tokens` stamped); 1 `partial` (news failed); 1 `failed`.                                                                                                        | market     |
| 4    | `seed_threads()` | 2 ready threads (1 pinned to snapshot, 1 plain); 1 thread with active compare (2 branches, both `done`); 1 thread with `tool_use` history; 1 empty ready-to-send.                                                                | snapshots  |
| 5    | `seed_observer()`| 2 schedules (1 active, 1 paused); 1 observer thread with 4 messages (2 success, 1 failed, 1 cost-cap-skip); 1 structured schedule; 1 diff-mode schedule.                                                                        | threads    |
| 6    | `seed_triggers()`| 3 triggers (`always-fires price>0`; `pct_change>5 window=1h`; complex `all/any/not` DSL); 1 with 5 firings across 3 days.                                                                                                       | observer   |
| 7    | `seed_analytics()`| 20 `AIRun` spread across 7 days × 3 providers with varied cost/duration; forward-return correlation data; 15 trigger firings for heatmap.                                                                                       | triggers   |

**Reset strategy:**
- Per-test: `@pytest.mark.django_db(transaction=True)` with a savepoint that rolls back.
- Redis: flushed once per lane (session-scoped `_flush_redis` fixture).
- Files/images/backups: `tmp_path` per test, discarded.

**Fixture surface (conftest.py):**
```python
@pytest.fixture
def minimal(db): seed_minimal(); yield
@pytest.fixture
def market(minimal): seed_market(); yield
@pytest.fixture
def snapshots(market): seed_snapshots(); yield
@pytest.fixture
def threads(snapshots): seed_threads(); yield
@pytest.fixture
def observer(threads): seed_observer(); yield
@pytest.fixture
def triggers(observer): seed_triggers(); yield
@pytest.fixture
def analytics(triggers): seed_analytics(); yield
```

Tests depend on only the rung they need: `def test_leaderboard(page, analytics): ...`.

---

## 4. UI lane test catalog (~50 tests)

Files under `e2e/ui/`. Each test is one browser journey; names follow `test_<feature>_<scenario>`.

### test_dashboard.py (3)
- `test_dashboard_renders_all_cards`
- `test_dashboard_empty_state`
- `test_dashboard_cost_tile_reflects_airuns`

### test_snapshots.py (5)
- `test_capture_all_sections_ok` (extends existing gold path)
- `test_capture_partial_failure_marks_sections` — scenario `news-503`
- `test_capture_oversized_image_returns_413`
- `test_snapshot_drill_down` — `/costs/snapshot/:id` renders per-section token + cost
- `test_snapshot_diff_endpoint_surfaced` — UI "Compare vs previous"

### test_threads.py (4)
- `test_threads_list_pagination_and_filter`
- `test_thread_create_plain_and_send`
- `test_thread_create_pinned_to_snapshot` — synthetic first user message visible
- `test_thread_stop_midstream` — `message_done` with `stopped=true`

### test_compare.py (2)
- `test_compare_two_branches_stream_and_cost` (extend existing)
- `test_compare_three_providers_routes_costs` — 3 branches, 3 tiles, sum total

### test_observer.py (5)
- `test_create_schedule_and_run_now` (extend existing)
- `test_schedule_pause_resume`
- `test_observer_structured_mode_produces_typed_card`
- `test_observer_diff_mode_sends_only_delta` — assert request token count <10% of full
- `test_observer_cost_cap_skip_emits_system_message`

### test_triggers.py (5)
- `test_create_simple_trigger_and_fire_now` (extend existing)
- `test_create_complex_dsl_all_any_not`
- `test_trigger_backtest_runs_against_ohlc`
- `test_trigger_cooldown_respected`
- `test_trigger_edit_preserves_firings`

### test_analytics.py (6)
- `test_analytics_page_renders_all_five_cards`
- `test_leaderboard_orders_by_forward_return`
- `test_leaderboard_zero_coverage_row`
- `test_cost_per_insight_card`
- `test_trigger_heatmap_renders_cells`
- `test_unusual_options_card_shows_triggers`

### test_watchlists.py (3)
- `test_watchlists_list_and_create`
- `test_watchlist_detail_add_remove_ticker`
- `test_market_ticker_page_renders_ohlc_and_news`

### test_profiles.py (2)
- `test_profile_create_with_memory_tools_thinking_flags`
- `test_profile_toggle_active`

### test_costs.py (3)
- `test_costs_today_tile`
- `test_costs_caps_editor_persists`
- `test_costs_csv_export_downloads_and_parses`

### test_backups.py (2)
- `test_backup_now_and_gzip_magic` (extend existing)
- `test_backup_restore_from_ui`

### test_export.py (2)
- `test_export_zip_and_manifest` (extend existing)
- `test_export_single_thread_endpoint`

### test_settings.py (2)
- `test_provider_api_key_save_round_trip_masked`
- `test_daily_and_monthly_cap_edit`

### test_schwab_oauth.py (2)
- `test_oauth_authorize_redirects_to_stub`
- `test_oauth_callback_persists_encrypted_token`

### test_files_and_citations.py (3)
- `test_file_upload_and_attach_to_thread`
- `test_delete_file_hits_anthropic_delete`
- `test_citation_renders_news_link`

### test_keyboard_and_palette.py (1)
- `test_g_shortcuts_and_cmd_k_navigate_all_top_level_routes`

### test_error_paths.py (5)
- `test_claude_5xx_during_stream_shows_error_toast` — scenario `claude-5xx-midstream`
- `test_provider_disabled_blocks_send_ai`
- `test_cap_exceeded_banner_on_compose`
- `test_network_offline_connection_dot_red`
- `test_validation_errors_on_trigger_editor_show_inline`

**Total UI: 50 tests.**

---

## 5. API, WS, visual, a11y, perf catalogs

### 5.1 API lane — httpx contracts (~25)

No browser. Each asserts status, response shape, and key invariants.

- **test_health.py** (2) — `/api/health/`, `/api/ready/`
- **test_market_contract.py** (4) — quotes, ohlc, chain, news shape
- **test_snapshots_contract.py** (3) — create→status→sections; `/diff/`; image serve bytes
- **test_threads_contract.py** (4) — create plain/pinned; stop; compare branches; single-thread export
- **test_observer_contract.py** (2) — schedule CRUD; `/api/observer/threads/<profile_id>/`
- **test_triggers_contract.py** (2) — CRUD + DSL validation; `/backtest/`
- **test_analytics_contract.py** (5) — leaderboard, cpi, heatmap, timeline, unusual-options
- **test_backups_contract.py** (1) — list/create/download
- **test_export_contract.py** (1) — start/list/download + manifest v=1
- **test_costs_caps.py** (1) — `check_monthly_cap` + `/api/costs/caps`
- **test_scenario_engine_disabled_in_prod.py** (1) — `X-E2E-Scenario` is a no-op when `MOCK_EXTERNAL=false`

### 5.2 WS lane — Channels assertions (~10)

`e2e/helpers/ws_client.py` opens a `websockets` connection, collects events into a list with timestamps, offers `wait_for_event(type, timeout)` and `assert_sequence([...])` helpers. Backend actions are triggered via httpx, then event ordering is asserted.

- `test_thread_stream_emits_started_deltas_done`
- `test_thread_stream_cost_event_carries_parent_message_id`
- `test_tool_use_loop_emits_tool_call_and_tool_result`
- `test_thinking_deltas_precede_text`
- `test_compare_costs_route_to_right_branch` — two `parent_message_id`s, two `cost` events
- `test_snapshot_progress_per_section` — 7 section events (any order); terminal status event last
- `test_notifications_trigger_fire_delivered`
- `test_notifications_observer_done_delivered`
- `test_notifications_backup_done_delivered`
- `test_ws_reconnect_replays_recent_events` — drop + reconnect within 5s, no gap

### 5.3 Visual lane (~20)

1280×800, `deviceScaleFactor: 1`, `colorScheme: light`. One baseline per route:

Dashboard; Settings (general + backups + export tabs); Watchlists list; Watchlist detail; Market ticker; Profiles; Snapshot composer (empty + with ready snapshot); Threads list; Thread detail (plain + compare); Observer timeline; Costs (today + snapshot drill); Schedules; Triggers list; Trigger editor; Analytics (all 5 cards); Backups; Export.

**Mask set (applied in `helpers/visual.py`):**
```python
DEFAULT_MASKS = lambda page: [
    page.get_by_test_id("cost-tile-today"),
    page.get_by_test_id("notification-bell"),
    page.locator(".timestamp"),
    page.locator("[data-chart] canvas"),
    page.get_by_test_id("breadcrumb-trail"),
]
```

**Stability helper:**
```python
def wait_for_stable(page):
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important}")
    page.wait_for_selector("[data-testid^='skeleton-']", state="detached")
```

**Baselines:**
- Live in `e2e/visual/__screenshots__/<test>/linux/<name>.png` (platform=linux suffix; chromium-on-Debian deterministic across dev+CI).
- Committed. `.gitattributes` marks `*.png` under `__screenshots__/` as binary.
- Pre-commit hook fails on baselines >500KB.
- Diff tolerance: `maxDiffPixelRatio: 0.02`. Retries: 2 (Playwright built-in).

**Update flow:**
```
make e2e-visual-update    # pytest e2e/visual/ --update-snapshots
git add e2e/visual/__screenshots__/
```

### 5.4 A11y lane (~15 + keyboard)

`axe-playwright-python` wrapped in `helpers/axe_runner.py`. Runs with `{runOnly: {type: "tag", values: ["wcag2a","wcag2aa"]}, resultTypes: ["violations"]}`. Only `critical` + `serious` impact violations fail the test; moderate/minor go to an informational JSON artifact.

**Per-route scan (parametrized):**

| path | rung | name |
|------|------|------|
| `/` | minimal | dashboard |
| `/snapshot` | minimal | snapshot_composer |
| `/threads` | threads | threads_list |
| `/threads/:id` | threads | thread_detail |
| `/threads/observer/:profileId` | observer | observer_timeline |
| `/schedules` | observer | schedules |
| `/triggers` | triggers | triggers_list |
| `/triggers/new` | minimal | trigger_editor |
| `/analytics` | analytics | analytics |
| `/watchlists` | market | watchlists |
| `/watchlists/:id` | market | watchlist_detail |
| `/profiles` | minimal | profiles |
| `/costs` | analytics | costs |
| `/settings/backups` | minimal | backups |
| `/settings/export` | threads | export |

**Keyboard-only journey** (`test_keyboard_only.py`): drives dashboard → snapshot → thread flow using only Tab/Shift+Tab/Enter/Esc/Arrow/Space. Asserts every interactive element is reachable and a visible focus ring is present at every step.

**Rule overrides** (`a11y_ignores.py`): explicit suppressions each requiring a TODO link and rationale. None at v1; list is empty. Any entry added later must be reviewed.

### 5.5 Perf lane (5)

Lighthouse via `lighthouse` npm CLI in the `frontend` container. Runs against **prod overlay** (`make prod`) — dev-server numbers are noise. 3 runs per route, median.

**Budgets** (`e2e/perf/budgets.json`):
```json
{
  "/": {"LCP": 2500, "CLS": 0.10, "TBT": 300, "performance": 0.85},
  "/snapshot": {"LCP": 2500, "CLS": 0.10, "TBT": 400, "performance": 0.80},
  "/threads/:id": {"LCP": 3000, "CLS": 0.10, "TBT": 400, "performance": 0.80},
  "/costs": {"LCP": 2500, "CLS": 0.10, "TBT": 300, "performance": 0.85},
  "/analytics": {"LCP": 3500, "CLS": 0.10, "TBT": 500, "performance": 0.75}
}
```

**Flake guard:** fail only if ≥2 of 3 runs miss the target.

---

## 6. Page Object Model

**Pattern:** locators as properties, actions as methods, **assertions live in tests**. POMs return locators or perform actions.

**Base** (`pages/base.py`):
```python
class BasePage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")
    def goto(self, path: str) -> None: ...
    def wait_ready(self) -> None: ...           # networkidle + no skeleton
    def expect_toast(self, text: str) -> None: ...
    def expect_error_boundary_absent(self) -> None: ...
    def open_command_palette(self) -> None: ...
    def run_shortcut(self, keys: str) -> None: ...
    def current_crumb_trail(self) -> list[str]: ...
```

**Concrete pages** — 18 classes, ~30–60 lines each:

| Page | Representative locators | Representative actions |
|---|---|---|
| `DashboardPage` | `.card-snapshots`, `.card-threads`, `.card-cost`, `notification_bell` | `open_notification_drawer()` |
| `SnapshotComposerPage` | `profile_select`, `objective_input`, `sections_checklist`, `capture_btn`, `send_ai_btn` | `capture(profile, objective, sections=None)`, `wait_for_complete(timeout)`, `send_to_ai()`, `open_compare()` |
| `ThreadsListPage` | `thread_row(id)`, `filter_input`, `pagination_next` | `open(id)`, `filter(text)` |
| `ThreadDetailPage` | `message(id)`, `stop_btn`, `compose`, `branch_tab(n)`, `cost_tile(branch)` | `send(text)`, `stop()`, `attach_file(path)`, `wait_for_done(timeout)` |
| `ObserverTimelinePage` | `fire_row`, `status_badge` | `scroll_to_day(date)` |
| `SchedulesPage` | `create_btn`, `interval_input`, `mode_select`, `structured_toggle`, `run_now_btn(id)`, `pause_btn(id)` | `create(interval, mode, structured)`, `run_now(id)`, `pause(id)` |
| `TriggersListPage` | `row(id)`, `new_btn`, `firings_tab` | `open(id)` |
| `TriggerEditorPage` | `name`, `ticker`, `metric`, `op`, `value`, `dsl_json`, `backtest_btn`, `fire_now_btn` | `fill_simple(...)`, `fill_dsl(json)`, `backtest(start, end)`, `save()` |
| `AnalyticsPage` | `card_leaderboard`, `card_cpi`, `card_heatmap`, `card_timeline`, `card_unusual(ticker)` | `set_ticker(sym)`, `set_forward_hours(n)` |
| `WatchlistsPage` | `list_item`, `create_btn` | `create(name)`, `open(name)` |
| `WatchlistDetailPage` | `ticker_row`, `add_input`, `remove_btn(ticker)` | `add(ticker)`, `remove(ticker)` |
| `MarketTickerPage` | `ohlc_chart`, `news_list`, `positions_tile` | — |
| `ProfilesPage` | `row(name)`, `tools_toggle`, `thinking_budget`, `memory_toggle` | `create(name, flags)`, `toggle_active(name)` |
| `CostsPage` | `today_tile`, `provider_table`, `csv_btn`, `caps_editor` | `export_csv()`, `set_caps(daily, monthly)` |
| `SnapshotCostPage` | `section_row(name)`, `cost_total` | — |
| `BackupsPage` | `backup_now_btn`, `row(id)`, `restore_btn(id)`, `download_btn(id)` | `backup_now()`, `restore(id)`, `download(id) -> bytes` |
| `ExportPage` | `start_btn`, `row(id)`, `download_btn(id)` | `start()`, `download(id) -> bytes` |
| `SettingsPage` | `api_key_input(provider)`, `save_btn`, `caps_inputs` | `save_api_key(provider, key)` |
| `SchwabOAuthPage` | `connect_btn`, `status_pill` | `connect()` |

**Selector strategy:**
1. `get_by_role(...)` / `get_by_label(...)` first.
2. `data-testid` only where role/label is ambiguous or dynamic.
3. Text-based selectors last.

**New testids to add to the frontend (single PR, no behavior change):**
`notification-bell`, `connection-status-dot`, `branch-cost-<n>`, `schedule-row-<id>`, `trigger-row-<id>`, `analytics-card-<kind>`, `snapshot-section-<name>`, `cost-tile-today`, `toast-<kind>`, `breadcrumb-trail`, `command-palette`, `skeleton-<where>`, `thread-row-<id>`, `file-row-<id>`, `profile-row-<name>`, `watchlist-row-<name>`, `firing-row-<id>`, `message-<id>`, `citation-<id>`, `section-<name>-status`, `capture-btn`, `send-ai-btn`, `backup-row-<id>`, `export-row-<id>`, `compose-input`. ≈25 additions.

---

## 7. Scenario engine

Extends `apps/core/mocks.py` into a small dispatch layer.

**Python surface** (`apps/core/mocks/__init__.py`):
```python
from contextvars import ContextVar

_scenario: ContextVar[str] = ContextVar("e2e_scenario", default="default")

def set_scenario(name: str) -> None: _scenario.set(name)
def current_scenario() -> str: return _scenario.get()


class ScenarioHeaderMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        if settings.MOCK_EXTERNAL and (s := request.headers.get("X-E2E-Scenario")):
            set_scenario(s)
        return self.get_response(request)
```

`ScenarioHeaderMiddleware` is added to `MIDDLEWARE` only when `MOCK_EXTERNAL=true` (guarded in `settings/base.py`). Prod deployments never load it.

**Registry** (`apps/core/mocks/scenarios.py`) — dict `{scenario: {service: handler}}`. Providers consult `current_scenario()` and dispatch to the matching handler; fallback to `default`.

**Initial scenarios (13):**

| Scenario | claude | openai | schwab | finnhub | files |
|---|---|---|---|---|---|
| `default` | streams "Mocked response" + usage | streams | ok | ok | ok |
| `claude-5xx` | 503 pre-stream | default | default | default | default |
| `claude-5xx-midstream` | 2 deltas then 500 | default | default | default | default |
| `claude-ratelimit` | 429 retry-after=30 | default | default | default | default |
| `openai-timeout` | default | hangs 60s | default | default | default |
| `schwab-401` | default | default | 401 token expired | default | default |
| `schwab-oauth-ok` | default | default | full oauth redirect/callback | default | default |
| `news-503` | default | default | default | 503 | default |
| `cap-exceeded` | default (intercepted in cost.py) | default | default | default | default |
| `files-upload-fail` | default | default | default | default | 500 on upload |
| `tool-use-loop` | streams tool_use → tool_result → text | default | default | default | default |
| `thinking-heavy` | streams thinking_delta* → text_delta* → done | default | default | default | default |
| `structured-observation` | returns ObservationReport-shaped JSON | default | default | default | default |

**Test client** (`e2e/mocks/client.py`):
```python
class ScenarioClient:
    def __init__(self, page, api_client):
        self.page = page
        self.api = api_client
    def use(self, name: str) -> None:
        self.page.set_extra_http_headers({"X-E2E-Scenario": name})
        self.api.headers["X-E2E-Scenario"] = name
```

**Guardrail:** `api/test_scenario_engine_disabled_in_prod.py` asserts that with `MOCK_EXTERNAL=false`, setting `X-E2E-Scenario: claude-5xx` has no effect.

---

## 8. Flake + failure strategy

### Retry policy

| Status | Retries | When |
|---|---|---|
| First-class (default) | 0 | If it fails, it fails. |
| Known-flaky | 2 | `@pytest.mark.flaky(reruns=2)`; requires linked issue in docstring. |
| Visual | 2 | Playwright built-in; pixel-diff jitter. |
| Perf | median of 3 | Built into runner. |

No blanket lane-level retries — flakiness is an issue to fix, not a setting to tune.

### Deadlines

| Lane | Per-test timeout | Playwright action | Navigation |
|------|------------------|-------------------|------------|
| UI | 60s | 10s | 15s |
| API | 30s | — | — |
| WS | 30s | — | — |
| Visual | 180s | 10s | 15s |
| A11y | 120s | 10s | 15s |
| Perf | 300s | — | — |

Set via `pytest-timeout`, overridable per-test. `expect(...).to_be_visible(timeout=N)` always explicit.

### On failure

Per-test artifacts:
- `playwright-traces/` — `.zip` per failing UI test (`--tracing=retain-on-failure`)
- `videos/` — failed UI tests only
- `screenshots/` — actual + expected + diff on visual failures
- `a11y-violations.json` — structured violations list
- `lighthouse-reports/` — HTML + JSON per failing route

### Console + network guard

Every UI test subscribes to `page.on("console")` and `page.on("pageerror")`. Any JS error or unhandled `console.error` fails the test regardless of assertion outcome. Unexpected 4xx/5xx network responses (outside scenario-engine-driven) also fail the test.

Known-noise allowlist lives in `conftest.py` (only entry at v1: `/render/chart` has a known warning).

### Flake audit

`tools/flake_audit.py` re-runs all lanes 3× nightly on main. Tests that pass 2/3 and fail 1/3 land in `flake_audit.json`. Weekly auto-opened issue lists the top-10 flakiest tests with links to their artifacts.

### Backend determinism

- Celery: eager (`CELERY_TASK_ALWAYS_EAGER=True`) in API lane; real Celery in UI/WS (needed for streaming/observer).
- `OBSERVER_TEST_MIN_INTERVAL_SECONDS=1`, `TRIGGER_TEST_COOLDOWN_SECONDS=1`, `TRIGGER_EVAL_INTERVAL_SECONDS=1` (new) in overlay.
- Clock: `freezegun.freeze_time(...)` in API/WS only (Playwright contexts don't support freezing). UI tests use relative dates.

---

## 9. Execution + CI

### Make targets

```
make e2e                 → all lanes sequentially (~20 min locally with xdist)
make e2e-ui              → UI lane only (~10 min)
make e2e-api             → API lane (~2 min)
make e2e-ws              → WS lane (~3 min)
make e2e-visual          → visual diffs (~5 min)
make e2e-visual-update   → regenerate baselines + print diff summary
make e2e-a11y            → axe scans (~3 min)
make e2e-perf            → Lighthouse (~5 min; requires prod overlay)
make e2e-one t=<path>    → single test
make e2e-up              → bring stack up with overlay, leave running
make e2e-down            → tear down
```

**Implementation:** each lane target is idempotent `docker compose ... up -d` → `pytest e2e/<lane>/ -n N -v`. Teardown is explicit.

**xdist per lane:** UI `-n 4 --dist=loadscope` (file-level browser reuse); API `-n 4`; WS `-n 2` (Channels group races); visual `-n 2`; a11y `-n 4`; perf serial.

### GitHub Actions

`.github/workflows/e2e.yml`:

```yaml
jobs:
  build-images:
    steps: [checkout, buildx build --load, docker save → artifact]
  e2e-ui:      needs: build-images  timeout-minutes: 20
  e2e-api:     needs: build-images  timeout-minutes: 10
  e2e-ws:      needs: build-images  timeout-minutes: 10
  e2e-visual:  needs: build-images  timeout-minutes: 15
  e2e-a11y:    needs: build-images  timeout-minutes: 10
  e2e-perf:    needs: build-images  timeout-minutes: 15
  e2e-summary:
    needs: [e2e-ui, e2e-api, e2e-ws, e2e-visual, e2e-a11y, e2e-perf]
    if: always()
    steps: [aggregate artifacts, post single PR comment with pass/fail matrix]
```

Wall time target: ~15 min.

### Local dev workflow

```
make e2e-up                          # first time: builds + starts
make e2e-one t=ui/test_snapshots.py::test_capture_all_sections_ok
HEADED=1 make e2e-one t=...          # visual debug
make e2e-down                        # when done
```

`HEADED=1` flips `playwright.chromium.launch(headless=False)` only when `TERM` indicates a real terminal (not CI).

---

## 10. Rollout sequencing

Eight phases. Each independently shippable, leaves main green.

| Phase | Scope | Est. |
|-------|-------|------|
| 0 | Scaffolding: new dirs, move+rename existing 6 journeys, expand conftest, make targets, GHA workflow skeleton, add ~25 data-testids to frontend (single no-behavior PR) | 2d |
| 1 | Seed ladder (7 rungs) + scenario engine + middleware + `test_scenario_engine_disabled_in_prod` | 3d |
| 2 | POM fill-out (18 pages) + API lane (25 tests) — fastest lane first so we have feedback early | 3d |
| 3 | UI lane gold paths (~25 tests): dashboard, snapshots gold, threads gold, compare gold, observer gold, triggers gold, analytics (all 6), watchlists, profiles, costs, backups, export gold, settings. Replaces existing journeys. | 4d |
| 4 | UI lane error + edge paths (~25 tests): error_paths, schwab_oauth, files_and_citations, keyboard_and_palette, and the error/edge branches within per-feature files (partial capture, stop-midstream, cooldown, cap-skip, etc.) | 3d |
| 5 | WS lane (10 tests) + `helpers/ws_client.py` | 3d |
| 6 | Visual lane (20 baselines) + `helpers/visual.py` + pre-commit size guard + update Make target | 2d |
| 7 | A11y (15 scans + keyboard-only) + Perf (5 Lighthouse routes + budgets) | 2d |
| 8 | Hardening: `tools/flake_audit.py`, artifact aggregator + PR comment, `e2e/README.md` runbook | 2d |

**Total: ~24 working days (~5 weeks)** for one developer. Phase 2 can partially overlap Phase 1. Phases 6 and 7 can run after Phase 3 lands.

### Explicitly out of scope (reiterated)
- Dark-mode visual snapshots
- Cross-browser matrix
- Real-provider canary lane
- Bundle-size / RUM
- Storybook + Chromatic
- Mutation / property-based testing
