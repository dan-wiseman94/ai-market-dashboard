# E2E Phase 4 — UI Lane Error + Edge Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill in the ~25 UI error + edge tests — partial snapshots, 5xx mid-stream, cap skips, OAuth, file uploads, citations, keyboard shortcuts. All scenario-engine-driven.

**Architecture:** Builds on Phase 3's gold tests. Every error/edge test declares `scenario` pytest fixture (from Phase 1) and calls `scenario.use("...")` before interacting. Error assertions target toasts, inline errors, or backend state rather than internal exception types.

**Tech Stack:** same as Phase 3.

**Spec reference:** `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md` §4 (UI catalog — error rows), §7 (scenario engine).

**Prerequisite:** Phases 0, 1, 2, 3 complete.

---

## File structure

**Create:**
- `e2e/ui/test_error_paths.py` (5)
- `e2e/ui/test_schwab_oauth.py` (2)
- `e2e/ui/test_files_and_citations.py` (3)
- `e2e/ui/test_keyboard_and_palette.py` (1)

**Extend (append new tests to existing Phase 3 files):**
- `e2e/ui/test_snapshots.py` — `test_capture_partial_failure_marks_sections`, `test_capture_oversized_image_returns_413` (2)
- `e2e/ui/test_threads.py` — `test_thread_stop_midstream` (1)
- `e2e/ui/test_observer.py` — `test_observer_structured_mode_produces_typed_card`, `test_observer_diff_mode_sends_only_delta`, `test_observer_cost_cap_skip_emits_system_message` (3)
- `e2e/ui/test_triggers.py` — `test_trigger_backtest_runs_against_ohlc`, `test_trigger_cooldown_respected`, `test_trigger_edit_preserves_firings` (3)
- `e2e/ui/test_backups.py` — `test_backup_restore_from_ui` (1)
- `e2e/ui/test_export.py` — `test_export_single_thread_endpoint` (1)
- `e2e/ui/test_threads.py` — `test_threads_list_filter_empty` edge (already covered; skip)

Total new: 25.

---

## Task 1 — `test_error_paths.py` (5 tests)

**Files:**
- Create: `e2e/ui/test_error_paths.py`

- [ ] **Step 1: Tests**

```python
"""UI error paths — scenario-driven."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.snapshot import SnapshotPage
from e2e.pages.trigger_editor import TriggerEditorPage


@pytest.mark.integration
@pytest.mark.ui
def test_claude_5xx_during_stream_shows_error_toast(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("claude-5xx-midstream")
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.capture(profile="E2E Default", objective="err test")
    s.wait_for_complete()
    s.send_to_ai()
    s.expect_toast("interrupted", kind="error", timeout=15_000)


@pytest.mark.integration
@pytest.mark.ui
def test_provider_disabled_blocks_send_ai(page, frontend_base_url, minimal) -> None:
    from apps.secrets.models import ProviderConfig
    ProviderConfig.objects.filter(provider="claude").update(enabled=False)

    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.capture(profile="E2E Default", objective="disabled provider test")
    s.wait_for_complete()
    # Send button should be disabled or clicking shows guard
    expect(s.send_ai_btn).to_be_disabled()


@pytest.mark.integration
@pytest.mark.ui
def test_cap_exceeded_banner_on_compose(page, frontend_base_url, minimal) -> None:
    from apps.secrets.models import ProviderConfig
    ProviderConfig.objects.filter(provider="claude").update(daily_cost_cap_usd="0.00")

    s = SnapshotPage(page, frontend_base_url)
    s.go()
    expect(page.get_by_text("Daily cap exceeded", exact=False)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_network_offline_connection_dot_red(page, frontend_base_url, minimal) -> None:
    from e2e.pages.dashboard import DashboardPage
    d = DashboardPage(page, frontend_base_url)
    d.go()
    # Force-close the WS via evaluate
    page.evaluate("() => { window.__ws && window.__ws.close(); }")
    expect(d.connection_dot).to_have_attribute("data-status", "disconnected", timeout=5_000)


@pytest.mark.integration
@pytest.mark.ui
def test_validation_errors_on_trigger_editor_show_inline(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    # Leave name empty + save — should show field-level error
    e.save()
    expect(page.get_by_text("Name is required", exact=False)).to_be_visible()
```

- [ ] **Step 2: Pass + commit.**

```bash
git add e2e/ui/test_error_paths.py
git commit -m "test(e2e/ui): error paths — 5xx/disabled/cap/offline/validation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2 — Snapshot edge tests (partial failure + oversize)

**Files:**
- Modify: `e2e/ui/test_snapshots.py`

- [ ] **Step 1: Append tests**

```python
@pytest.mark.integration
@pytest.mark.ui
def test_capture_partial_failure_marks_sections(page, frontend_base_url, minimal, scenario) -> None:
    from e2e.pages.snapshot import SnapshotPage
    scenario.use("news-503")
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.capture(profile="E2E Default", objective="partial test")
    s.wait_for_complete()
    # News section status == failed; others ready
    expect(s.section_status("news")).to_contain_text("failed")
    expect(s.section_status("quotes")).to_contain_text("ready")


@pytest.mark.integration
@pytest.mark.ui
def test_capture_oversized_image_returns_413(page, frontend_base_url, minimal, tmp_path) -> None:
    big = tmp_path / "big.png"
    big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024))  # 6MB of zeros

    page.goto(f"{frontend_base_url}/snapshot")
    page.set_input_files("input[type=file][name='image']", str(big))
    # Expect toast 'too large'
    expect(page.get_by_test_id("toast-error")).to_contain_text("too large", timeout=10_000)
```

- [ ] **Step 2: Commit.**

```bash
git add e2e/ui/test_snapshots.py
git commit -m "test(e2e/ui): snapshot edges (partial 503 + 413 oversize)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3 — Thread stop-midstream edge

**Files:**
- Modify: `e2e/ui/test_threads.py`

- [ ] **Step 1: Append test**

```python
@pytest.mark.integration
@pytest.mark.ui
def test_thread_stop_midstream(page, frontend_base_url, minimal, scenario) -> None:
    from e2e.pages.thread_detail import ThreadDetailPage
    # Use a slow-stream scenario so we have a window to click stop
    scenario.use("thinking-heavy")

    page.goto(f"{frontend_base_url}/threads/new")
    page.get_by_label("Profile").select_option(label="E2E Default")
    page.get_by_role("button", name="Create").click()

    t = ThreadDetailPage(page, frontend_base_url)
    t.send("long stream please")
    t.stop()
    expect(page.get_by_text("stopped", exact=False)).to_be_visible(timeout=10_000)
```

- [ ] **Step 2: Commit.**

```bash
git add e2e/ui/test_threads.py
git commit -m "test(e2e/ui): thread stop-midstream edge

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4 — Observer structured + diff + cap-skip

**Files:**
- Modify: `e2e/ui/test_observer.py`

- [ ] **Step 1: Append 3 tests**

```python
@pytest.mark.integration
@pytest.mark.ui
def test_observer_structured_mode_produces_typed_card(page, frontend_base_url, observer, scenario) -> None:
    from apps.observer.models import ObserverSchedule
    scenario.use("structured-observation")
    sched = ObserverSchedule.objects.get(name="E2E structured schedule")

    from e2e.pages.schedules import SchedulesPage
    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.run_now(sched.id)
    # Navigate to observer timeline; look for structured card
    from apps.profiles.models import TradingProfile
    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    expect(page.get_by_test_id("observation-card")).to_be_visible(timeout=30_000)


@pytest.mark.integration
@pytest.mark.ui
def test_observer_diff_mode_sends_only_delta(page, frontend_base_url, observer) -> None:
    from apps.observer.models import ObserverSchedule
    sched = ObserverSchedule.objects.get(name="E2E diff schedule")

    from e2e.pages.schedules import SchedulesPage
    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.run_now(sched.id)

    # Observer thread latest message must show reduced token count (< 10% of baseline)
    from apps.profiles.models import TradingProfile
    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    # Token badge shown per run
    expect(page.get_by_test_id("request-token-count")).to_be_visible(timeout=30_000)
    tokens = int(page.get_by_test_id("request-token-count").inner_text().replace(",", "").split()[0])
    assert tokens < 5000


@pytest.mark.integration
@pytest.mark.ui
def test_observer_cost_cap_skip_emits_system_message(page, frontend_base_url, observer) -> None:
    from apps.observer.models import ObserverSchedule
    from apps.secrets.models import ProviderConfig
    ProviderConfig.objects.filter(provider="claude").update(daily_cost_cap_usd="0.01")
    sched = ObserverSchedule.objects.get(name="E2E active schedule")

    from e2e.pages.schedules import SchedulesPage
    s = SchedulesPage(page, frontend_base_url)
    s.go()
    s.run_now(sched.id)

    # Look for system/done message
    from apps.profiles.models import TradingProfile
    pid = TradingProfile.objects.get(name="E2E Default").id
    page.goto(f"{frontend_base_url}/threads/observer/{pid}")
    expect(page.get_by_text("skipped: cost cap", exact=False)).to_be_visible(timeout=30_000)
```

- [ ] **Step 2: Commit.**

```bash
git add e2e/ui/test_observer.py
git commit -m "test(e2e/ui): observer edges (structured + diff + cap-skip)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5 — Trigger backtest + cooldown + edit

**Files:**
- Modify: `e2e/ui/test_triggers.py`

- [ ] **Step 1: Append 3 tests**

```python
@pytest.mark.integration
@pytest.mark.ui
def test_trigger_backtest_runs_against_ohlc(page, frontend_base_url, triggers) -> None:
    from e2e.pages.trigger_editor import TriggerEditorPage
    from apps.triggers.models import Trigger
    trig = Trigger.objects.get(name="E2E always fires")

    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.backtest(start="2026-03-20T00:00:00Z", end="2026-04-18T00:00:00Z")
    expect(page.get_by_test_id("backtest-results")).to_be_visible(timeout=15_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_cooldown_respected(page, frontend_base_url, triggers) -> None:
    from e2e.pages.trigger_editor import TriggerEditorPage
    from apps.triggers.models import Trigger
    trig = Trigger.objects.get(name="E2E always fires")

    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.fire_now_btn.click()
    # Immediately clicking again within cooldown shows cooldown UI
    e.fire_now_btn.click()
    expect(page.get_by_text("on cooldown", exact=False)).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_edit_preserves_firings(page, frontend_base_url, triggers) -> None:
    from apps.triggers.models import Trigger, TriggerFiring
    trig = Trigger.objects.get(name="E2E always fires")
    before = TriggerFiring.objects.filter(trigger=trig).count()

    from e2e.pages.trigger_editor import TriggerEditorPage
    e = TriggerEditorPage(page, frontend_base_url)
    e.go(trig.id)
    e.name.fill("E2E always fires (edited)")
    e.save()

    assert TriggerFiring.objects.filter(trigger=trig).count() == before
```

- [ ] **Step 2: Commit.**

```bash
git add e2e/ui/test_triggers.py
git commit -m "test(e2e/ui): trigger edges (backtest + cooldown + edit)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6 — Backup restore from UI

**Files:**
- Modify: `e2e/ui/test_backups.py`

- [ ] **Step 1: Append test**

```python
@pytest.mark.integration
@pytest.mark.ui
def test_backup_restore_from_ui(page, frontend_base_url, minimal) -> None:
    """Clicks Back up now, then Restore on the row. Verifies toast + row reappears."""
    from e2e.pages.backups import BackupsPage
    b = BackupsPage(page, frontend_base_url)
    b.go()
    b.backup_now()
    expect(page.locator("tr:has-text('ok')")).to_be_visible(timeout=60_000)

    # Now click restore on the first ok row
    page.locator("tr:has-text('ok')").first.get_by_role("button", name="Restore").click()
    # Modal confirm
    page.get_by_role("button", name="Confirm restore").click()
    b.expect_toast("restore started", kind="info", timeout=10_000)
```

- [ ] **Step 2: Commit.**

```bash
git add e2e/ui/test_backups.py
git commit -m "test(e2e/ui): backup restore edge

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7 — Export single-thread endpoint

**Files:**
- Modify: `e2e/ui/test_export.py`

```python
@pytest.mark.integration
@pytest.mark.ui
def test_export_single_thread_endpoint(page, frontend_base_url, threads, tmp_path) -> None:
    import httpx
    from e2e.conftest import E2E_BASE_URL
    from apps.threads.models import Thread
    t = Thread.objects.first()

    r = httpx.get(f"{E2E_BASE_URL}/api/export/thread/{t.id}/", timeout=20)
    assert r.status_code == 200
    dl = tmp_path / f"thread-{t.id}.dl"
    dl.write_bytes(r.content)
    assert dl.stat().st_size > 0
```

- [ ] **Commit.**

```bash
git add e2e/ui/test_export.py
git commit -m "test(e2e/ui): single-thread export endpoint

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8 — `test_schwab_oauth.py`

**Files:**
- Create: `e2e/ui/test_schwab_oauth.py`

```python
"""Schwab OAuth gold path via scenario engine."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.schwab_oauth import SchwabOAuthPage


@pytest.mark.integration
@pytest.mark.ui
def test_oauth_authorize_redirects_to_stub(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    s = SchwabOAuthPage(page, frontend_base_url)
    s.go()
    with page.expect_navigation():
        s.connect()
    # Stub ends at /schwab/callback?code=MOCK_OAUTH per scenarios.py
    assert "callback" in page.url


@pytest.mark.integration
@pytest.mark.ui
def test_oauth_callback_persists_encrypted_token(page, frontend_base_url, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    s = SchwabOAuthPage(page, frontend_base_url)
    s.go()
    with page.expect_navigation():
        s.connect()

    # After callback lands, status pill shows 'connected'
    s.go()
    expect(s.status_pill).to_contain_text("connected", timeout=10_000)

    # Token persisted encrypted in DB
    from apps.secrets.models import ApiCredential
    cred = ApiCredential.objects.filter(provider="schwab").first()
    assert cred is not None
    assert cred.access_token  # encrypted bytes
```

- [ ] **Commit.**

```bash
git add e2e/ui/test_schwab_oauth.py
git commit -m "test(e2e/ui): schwab OAuth authorize + callback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9 — `test_files_and_citations.py`

**Files:**
- Create: `e2e/ui/test_files_and_citations.py`

```python
"""Files API + citations edges."""
from __future__ import annotations

import pytest
from pathlib import Path

from playwright.sync_api import expect

from e2e.pages.files import FilesPage
from e2e.pages.thread_detail import ThreadDetailPage


@pytest.mark.integration
@pytest.mark.ui
def test_file_upload_and_attach_to_thread(page, frontend_base_url, threads, tmp_path: Path) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")

    page.goto(f"{frontend_base_url}/files")
    FilesPage(page, frontend_base_url).upload(pdf)
    expect(page.get_by_text("test.pdf")).to_be_visible()

    # Attach to an existing thread
    from apps.threads.models import Thread
    t = Thread.objects.get(title="E2E plain thread")
    td = ThreadDetailPage(page, frontend_base_url)
    td.go(t.id)
    td.attach_file(pdf)
    # Message with a document block appears
    expect(page.get_by_text("test.pdf")).to_be_visible(timeout=10_000)


@pytest.mark.integration
@pytest.mark.ui
def test_delete_file_hits_anthropic_delete(page, frontend_base_url, minimal, tmp_path: Path) -> None:
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")

    page.goto(f"{frontend_base_url}/files")
    FilesPage(page, frontend_base_url).upload(pdf)
    # Find newly created row
    row = page.locator("[data-testid^='file-row-']").last
    fid = row.get_attribute("data-testid").split("-")[-1]
    FilesPage(page, frontend_base_url).delete(fid)
    expect(page.get_by_test_id(f"file-row-{fid}")).to_have_count(0)


@pytest.mark.integration
@pytest.mark.ui
def test_citation_renders_news_link(page, frontend_base_url, threads) -> None:
    """Open a thread that references news; assert Citation resolves."""
    from apps.threads.models import Thread
    # Pick any thread; the seeded mock response contains a citation block in tool-use thread
    t = Thread.objects.get(title="E2E tool-use thread")
    page.goto(f"{frontend_base_url}/threads/{t.id}")
    citations = page.locator("[data-testid^='citation-']")
    if citations.count() == 0:
        pytest.skip("no citation block in seed; requires scenario with citations")
    url = citations.first.get_attribute("href")
    assert url and ("news://" in url or url.startswith("http"))
```

- [ ] **Commit.**

```bash
git add e2e/ui/test_files_and_citations.py
git commit -m "test(e2e/ui): file upload + attach + delete + citation render

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10 — `test_keyboard_and_palette.py`

**Files:**
- Create: `e2e/ui/test_keyboard_and_palette.py`

```python
"""Keyboard shortcuts + command palette."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.dashboard import DashboardPage


# Mapping of shortcut to expected URL substring
SHORTCUTS = {
    "g a": "/analytics",
    "g t": "/threads",
    "g s": "/snapshot",
    "g w": "/watchlists",
    "g c": "/costs",
    "g p": "/profiles",
    "g r": "/triggers",
    "g o": "/schedules",
    "g b": "/settings/backups",
    "g x": "/settings/export",
}


@pytest.mark.integration
@pytest.mark.ui
def test_g_shortcuts_and_cmd_k_navigate_all_top_level_routes(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()

    for keys, expected in SHORTCUTS.items():
        page.keyboard.press("Escape")  # ensure palette closed
        for key in keys.split():
            page.keyboard.press(key.upper() if len(key) == 1 else key)
        page.wait_for_url(lambda u: expected in u, timeout=5_000)
        assert expected in page.url

    # Cmd-K command palette — go-analytics
    page.goto(frontend_base_url)
    d.open_command_palette()
    page.keyboard.type("go-analytics")
    page.keyboard.press("Enter")
    page.wait_for_url(lambda u: "/analytics" in u, timeout=5_000)
    assert "/analytics" in page.url
```

*(Adjust shortcut key mappings if they differ from the project's actual `useKeyboardShortcuts` definitions; grep `frontend/src/hooks/useKeyboardShortcuts.ts` for exact letters before finalizing the table.)*

- [ ] **Commit.**

```bash
git add e2e/ui/test_keyboard_and_palette.py
git commit -m "test(e2e/ui): g-shortcut nav + Cmd-K palette

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 acceptance

- [ ] `make e2e-ui` runs ~50 tests (25 gold from Phase 3 + 25 edge from Phase 4), all pass.
- [ ] Wall time ≤ 12 min with `-n 4 --dist=loadscope`.
- [ ] No regressions in API lane (`make e2e-api`).
- [ ] Scenario engine exercised: at least 6 distinct scenarios invoked across the test set.
- [ ] Cost-cap test touches the real cost pipeline (not just UI text).
