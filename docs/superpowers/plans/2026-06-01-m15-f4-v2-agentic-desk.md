# M15 F4 v2 — Agentic Desk (tool-grounded investigations + executable actions) Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkboxes per step. Branch: `feat/m15-v2` (off merged main).

**Goal:** Upgrade the Desk (`apps.desk`) v1 (synchronous `run_structured` findings, one executable action) to v2: **real M14 tool-grounded agentic investigations** (reuse `run_ai_on_message(investigate=True)`), an **executable "Revise coverage" action**, and an **opt-in L3 auto-execute** path.

**Architecture:** `investigate()` stops calling `run_structured` and instead originates a real bounded investigation — a `Thread` + synthetic user message + `run_ai_on_message(..., investigate=True)` (the shipped M14 `_apply_investigation_mode` tool loop) — then reads the resulting assistant message as the finding and links the thread. The act endpoint gains `revise_coverage` (latest ready snapshot → `coverage.revise_coverage`). A new `AUTONOMY_AUTO_EXECUTE` setting (default OFF) lets the sweep auto-act on high-severity findings.

**Conventions:** same as M15 v1 (Docker `-p ws-since-replay`; `-u 1000:1000` for makemigrations; frontend one-off `docker run`; serializer Meta `ClassVar`; commit locally + Claude trailer; patch `run_ai_on_message` / `run_structured` in tests).

---

## Task 1: `DeskEntry.investigation_thread` FK

**Files:** `backend/apps/desk/models.py`, migration, `tests/test_model_v2.py`.

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_model_v2.py`:
```python
import pytest

from apps.desk.models import DeskEntry
from apps.threads.models import Thread

pytestmark = pytest.mark.django_db


def test_investigation_thread_fk():
    th = Thread.objects.create(kind="consult", title="Investigate NVDA")
    e = DeskEntry.objects.create(anomaly_type="price_move", ticker="NVDA", severity=9.0, investigation_thread=th)
    assert e.investigation_thread_id == th.id
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** add to `DeskEntry` (in `backend/apps/desk/models.py`), after `warroom_run`:
```python
    investigation_thread = models.ForeignKey(
        "threads.Thread", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
```

- [ ] **Step 4:** `makemigrations desk` (`-u 1000:1000`); confirm `dan`-owned.
- [ ] **Step 5:** run → PASS.
- [ ] **Step 6:** commit `feat(desk): DeskEntry.investigation_thread FK (M15 F4 v2)`.

---

## Task 2: Agentic investigation (reuse the M14 tool loop)

**Files:** `backend/apps/desk/services/investigate.py` (rewrite), `tests/test_investigate.py` (update).

- [ ] **Step 1: replace the test** `backend/apps/desk/tests/test_investigate.py`:
```python
import pytest

from apps.desk.services import investigate as I
from apps.threads.models import Message, Thread

pytestmark = pytest.mark.django_db

CAND = {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 8.0, "evidence": {"pct_change": 8.0}}


def test_no_provider_returns_none(monkeypatch):
    # No claude config + run_ai_on_message that writes nothing -> None.
    monkeypatch.setattr(I, "run_ai_on_message", lambda **kw: {"status": "failed"})
    assert I.investigate(CAND) is None


def test_investigate_runs_bounded_investigation(monkeypatch):
    captured = {}

    def _fake_run(**kw):
        captured.update(kw)
        # simulate the investigation writing its assistant finding into the thread
        Message.objects.create(
            thread_id=kw["thread_id"], role="assistant", status="done",
            content={"text": "NVDA gapped on capex; breakout retest in play.", "kind": "investigation"},
        )
        return {"status": "done"}

    monkeypatch.setattr(I, "run_ai_on_message", _fake_run)
    out = I.investigate(CAND)
    assert out is not None
    assert "NVDA gapped" in out["finding"]
    assert captured["investigate"] is True  # used the bounded tool loop
    th = Thread.objects.get(id=out["investigation_thread_id"])
    assert th.kind == "consult"
    # a synthetic user message carried the anomaly context
    assert Message.objects.filter(thread=th, role="user").exists()
    # the convene_warroom action is still offered
    assert out["suggested_actions"][0]["type"] == "convene_warroom"
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** rewrite `backend/apps/desk/services/investigate.py`:
```python
"""Agentic per-anomaly investigation (M15 F4 v2). Originates a REAL bounded
investigation via the M14 tool loop (run_ai_on_message investigate=True) in a
fresh thread, then reads the assistant finding. Returns
{finding, suggested_actions, investigation_thread_id} or None when nothing was
produced (no provider / cap / error — run_ai_on_message degrades internally)."""

from __future__ import annotations

import logging

from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def _prompt(cand: dict) -> str:
    return (
        f"An automated sweep flagged this market anomaly:\n"
        f"- type: {cand.get('anomaly_type')}\n- ticker: {cand.get('ticker') or '(book-wide)'}\n"
        f"- evidence: {cand.get('evidence')}\n\n"
        "Investigate it using your tools (quotes, news, recall, etc.): what is it, what does it "
        "imply for our view, and what (if anything) is worth doing? Strictly observational."
    )


def investigate(cand: dict) -> dict | None:
    thread = Thread.objects.create(kind="consult", title=f"Investigation: {cand.get('anomaly_type')} {cand.get('ticker') or 'book'}"[:200])
    user_msg = Message.objects.create(thread=thread, role="user", status="done", content={"text": _prompt(cand)})

    try:
        # Synchronous (we're already inside the sweep worker); investigate=True forces the
        # bounded M14 tool loop. Degrades internally (no key / cap / error) -> no assistant msg.
        run_ai_on_message(thread_id=thread.id, user_message_id=user_msg.id, investigate=True)
    except Exception:
        log.warning("desk.investigate.run_failed", exc_info=True)

    assistant = (
        Message.objects.filter(thread=thread, role="assistant", status="done")
        .order_by("-created_at")
        .first()
    )
    if assistant is None:
        return None
    finding = (assistant.content or {}).get("text", "").strip() if isinstance(assistant.content, dict) else ""
    if not finding:
        return None

    subj = cand.get("ticker") or "the book"
    actions = [
        {"type": "convene_warroom", "label": f"Convene War Room on {subj}",
         "params": {"free_prompt": f"Debate: {finding[:500]}"}},
    ]
    if cand.get("ticker"):
        actions.append({"type": "revise_coverage", "label": f"Revise coverage on {cand['ticker']}",
                        "params": {"ticker": cand["ticker"]}})
    return {"finding": finding, "suggested_actions": actions, "investigation_thread_id": thread.id}
```

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): agentic tool-grounded investigation via run_ai_on_message (M15 F4 v2)`.

---

## Task 3: Sweep persists the investigation thread

**Files:** `backend/apps/desk/services/sweep.py`, `tests/test_sweep.py` (update one assertion).

- [ ] **Step 1: extend the test** — in `backend/apps/desk/tests/test_sweep.py`, change the `investigate` monkeypatch to also return `investigation_thread_id` and assert it's stored:
```python
def test_sweep_links_investigation_thread(monkeypatch):
    from apps.threads.models import Thread

    th = Thread.objects.create(kind="consult", title="t")
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA"])
    monkeypatch.setattr(S, "run_detectors", lambda uni: [{"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}}])
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": [], "investigation_thread_id": th.id})
    S.run_sweep(top_k=1)
    from apps.desk.models import DeskEntry
    assert DeskEntry.objects.first().investigation_thread_id == th.id
```
(The existing `test_sweep_*` tests pass `{"finding": ..., "suggested_actions": []}` with no `investigation_thread_id`; make `sweep` tolerate its absence via `.get`.)

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** in `backend/apps/desk/services/sweep.py`, in the `DeskEntry.objects.create(...)` call, add:
```python
            investigation_thread_id=result.get("investigation_thread_id"),
```

- [ ] **Step 4:** run the full `apps/desk/tests/test_sweep.py` → PASS (old + new).
- [ ] **Step 5:** commit `feat(desk): link the investigation thread on sweep entries (M15 F4 v2)`.

---

## Task 4: Executable "Revise coverage" action

**Files:** `backend/apps/desk/views.py`, `backend/apps/desk/serializers.py` (expose `investigation_thread_id`), `tests/test_views_v2.py`.

- [ ] **Step 1: failing test** `backend/apps/desk/tests/test_views_v2.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.desk.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_serializer_exposes_investigation_thread():
    from apps.threads.models import Thread

    th = Thread.objects.create(kind="consult", title="t")
    e = DeskEntry.objects.create(anomaly_type="x", ticker="NVDA", severity=1.0, investigation_thread=th)
    body = APIClient().get(f"/api/desk/{e.id}/").json()
    assert body["investigation_thread_id"] == th.id


def test_act_revise_coverage(monkeypatch):
    from apps.desk import views

    e = DeskEntry.objects.create(anomaly_type="coverage_stale", ticker="NVDA", severity=8.0, finding="stale",
                                 suggested_actions=[{"type": "revise_coverage", "label": "Revise", "params": {"ticker": "NVDA"}}])
    called = {}
    monkeypatch.setattr(views, "_revise_coverage_action", lambda ticker: called.setdefault("t", ticker) or True)
    resp = APIClient().post(f"/api/desk/{e.id}/act/", {"action": "revise_coverage"}, format="json")
    assert resp.status_code == 200
    assert called["t"] == "NVDA"
    e.refresh_from_db()
    assert e.status == "acted"
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3a:** in `backend/apps/desk/serializers.py`, add `"investigation_thread_id"` to the `fields` list.

- [ ] **Step 3b:** in `backend/apps/desk/views.py`, add a module-level helper + an `act` branch:
```python
def _revise_coverage_action(ticker: str) -> bool:
    """Best-effort: revise the house view on `ticker` using its latest ready snapshot
    + the first available profile. Returns True if a revision attempt ran."""
    from apps.coverage.services.revise import revise_coverage
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot

    snap = (
        Snapshot.objects.filter(primary_ticker=ticker.upper(), status="ready")
        .order_by("-captured_at")
        .first()
    )
    if snap is None:
        return False
    profile = TradingProfile.objects.first()
    revise_coverage(ticker.upper(), snap, profile=profile)
    return True
```
and in `act`, after the `convene_warroom` branch, add:
```python
        elif request.data.get("action") == "revise_coverage":
            ticker = ""
            for a in entry.suggested_actions or []:
                if a.get("type") == "revise_coverage":
                    ticker = (a.get("params") or {}).get("ticker", "")
                    break
            if ticker:
                _revise_coverage_action(ticker)
                entry.status = "acted"
                entry.save(update_fields=["status"])
```
(Verify `Snapshot` has `primary_ticker` + `status="ready"` + `captured_at` — adjust the query to the real fields; the coach uses `snapshot.primary_ticker` and CLAUDE.md says the parent Snapshot terminal state is `"ready"`.)

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): executable revise-coverage act + expose investigation thread (M15 F4 v2)`.

---

## Task 5: Opt-in L3 auto-execute

**Files:** `backend/config/settings/base.py` (`AUTONOMY_AUTO_EXECUTE` default OFF), `backend/apps/desk/services/sweep.py`, `tests/test_autoexecute.py`.

- [ ] **Step 1:** add `AUTONOMY_AUTO_EXECUTE = env.bool("AUTONOMY_AUTO_EXECUTE", default=False)` near `ANOMALY_SWEEP_ENABLED` (match the file's env pattern).

- [ ] **Step 2: failing test** `backend/apps/desk/tests/test_autoexecute.py`:
```python
import pytest
from django.test import override_settings

from apps.desk.models import DeskEntry
from apps.desk.services import sweep as S

pytestmark = pytest.mark.django_db


def _seed(monkeypatch, severity):
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA"])
    monkeypatch.setattr(S, "run_detectors", lambda uni: [{"anomaly_type": "price_move", "ticker": "NVDA", "severity": severity, "evidence": {}}])
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": [{"type": "convene_warroom", "label": "x", "params": {"free_prompt": "p"}}], "investigation_thread_id": None})


@override_settings(AUTONOMY_AUTO_EXECUTE=False)
def test_no_autoexecute_by_default(monkeypatch):
    _seed(monkeypatch, 9.0)
    monkeypatch.setattr(S, "_auto_execute", lambda entry: (_ for _ in ()).throw(AssertionError("should not be called")))
    S.run_sweep(top_k=1)
    assert DeskEntry.objects.first().status == "new"


@override_settings(AUTONOMY_AUTO_EXECUTE=True)
def test_autoexecute_high_severity(monkeypatch):
    _seed(monkeypatch, 9.0)
    calls = []
    monkeypatch.setattr(S, "_auto_execute", lambda entry: calls.append(entry.id))
    S.run_sweep(top_k=1)
    assert len(calls) == 1
```

- [ ] **Step 3:** run → FAIL.

- [ ] **Step 4:** in `backend/apps/desk/services/sweep.py`:
```python
from django.conf import settings
from apps.desk import constants as C  # already imported

AUTO_EXECUTE_MIN_SEVERITY = 8.0


def _auto_execute(entry) -> None:
    """L3: auto-convene a War Room on a high-severity finding (the safe auto-action;
    auto-revise stays manual). Best-effort."""
    from apps.warroom.services.convene import convene

    for a in entry.suggested_actions or []:
        if a.get("type") == "convene_warroom":
            run = convene(free_prompt=(a.get("params") or {}).get("free_prompt") or f"Debate: {entry.finding}")
            entry.warroom_run = run
            entry.status = "acted"
            entry.save(update_fields=["warroom_run", "status"])
            return
```
and in `run_sweep`, right after the `_notify(entry)` block (inside the loop, after `created += 1`):
```python
        if getattr(settings, "AUTONOMY_AUTO_EXECUTE", False) and entry.severity >= AUTO_EXECUTE_MIN_SEVERITY:
            try:
                _auto_execute(entry)
            except Exception:
                log.warning("desk.auto_execute_failed", exc_info=True)
```

- [ ] **Step 5:** run → PASS; then `pytest apps/desk -q` (regression).
- [ ] **Step 6:** commit `feat(desk): opt-in L3 auto-execute (AUTONOMY_AUTO_EXECUTE, default OFF) (M15 F4 v2)`.

---

## Task 6: Frontend — investigation link + revise-coverage action

**Files:** `frontend/src/api/desk.ts` (+ `investigation_thread_id`), `frontend/src/pages/DeskPage.tsx`, `frontend/src/__tests__/DeskPage.v2.test.tsx`.

- [ ] **Step 1:** add `investigation_thread_id: number | null;` to the `DeskEntry` interface in `frontend/src/api/desk.ts`.

- [ ] **Step 2: failing test** `frontend/src/__tests__/DeskPage.v2.test.tsx`:
```tsx
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import DeskPage from "@/pages/DeskPage";
import { renderWithProviders } from "./testUtils";

describe("DeskPage v2", () => {
  it("shows a revise-coverage action + investigation link", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "x", anomaly_type: "coverage_stale", ticker: "NVDA", severity: 8, evidence: {}, finding: "stale", suggested_actions: [{ type: "revise_coverage", label: "Revise coverage on NVDA" }], status: "new", warroom_run_id: null, investigation_thread_id: 42 },
    ]);
    renderWithProviders(<DeskPage />);
    await waitFor(() => expect(screen.getByText(/Revise coverage on NVDA/)).toBeInTheDocument());
    expect(screen.getByText(/investigation/i)).toBeInTheDocument();  // link to the investigation thread
  });
});
```

- [ ] **Step 3:** in `DeskPage.tsx`: (a) render a `revise_coverage` action button (mirroring the `convene_warroom` button, calling `act.mutateAsync({id, action: "revise_coverage"})`); (b) when `e.investigation_thread_id` is set, render a `<Link to={`/threads/${e.investigation_thread_id}`}>View investigation</Link>`. Keep the convene button.

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(desk): frontend revise-coverage action + investigation link (M15 F4 v2)`.

---

## Final verification (F4 v2)
- `pytest apps/desk -q` + `pytest apps/threads -q` (investigate now drives run_ai_on_message)
- ruff check + format on apps/desk (`-u 1000:1000 -e RUFF_CACHE_DIR=/tmp/ruff`)
- Frontend vitest: useDesk + DeskPage + DeskPage.v2

## Self-review
- Agentic investigation (reuse M14 `run_ai_on_message investigate=True`) → Task 2. ✓
- Investigation thread linked + surfaced → Tasks 1, 3, 4, 6. ✓
- Executable revise-coverage → Task 4. ✓ (uses latest ready Snapshot; if none, no-op)
- Opt-in L3 auto-execute (default OFF) → Task 5. ✓
- Open-thesis executable action remains deferred (a frontend prefill, not a backend action) — documented.
