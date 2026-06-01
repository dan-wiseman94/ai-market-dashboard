# M15 F3 v2 — Streaming, Multi-Provider, Tool-Grounded War Room Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Branch `feat/m15-v2`. **High-risk phase** — touches the async AI pipeline; the controller reviews the convene-rewrite + run_debate task especially closely (consider inline for those).

**Goal:** Upgrade War Room v1 (Claude-only, synchronous `run_structured` personas) to v2: personas become **real streaming runs through `run_ai_on_message`** — **multi-provider** (via the `override={"provider","model"}` dict, the `compare` precedent), **tool-grounded** (`investigate=True` → the M14 bounded loop), and **live-streamed** into the `warroom` thread. The debate runs **async** (a `warroom.run_debate` Celery task); the synthesizer verdict stays `run_structured` (Claude, structured) reading the persona messages.

**Architecture:**
- `convene()` becomes thin: create the `WarRoomRun` (+`warroom` thread) with `status="running"` and dispatch `warroom.run_debate.delay(run_id)`; return immediately.
- `run_debate(run_id)` (new Celery task) orchestrates: for each persona (assigned a provider by `voice_mode`), post a synthetic user message (persona framing + subject + prior args) → `run_ai_on_message(thread_id, user_message_id, override={provider,model}, investigate=grounding)` → stamp `content["persona"]` on the resulting assistant message. Then `synthesize()` (unchanged `run_structured`) reads the persona messages → verdict; mark the run `done`.
- Each persona run **live-streams** via the existing `thread.<id>` pipeline; the courtroom subscribes to it.

**Why this is low-surgery:** no change to `run_ai_on_message`'s signature — it already accepts `override` (provider/model) and `investigate` (tools). Persona framing rides in the **user** message, so no system-prompt override is needed. The only pipeline touch is *consuming* existing params.

**Conventions:** as M15 v1. Tests: `CELERY_TASK_ALWAYS_EAGER` is on, so `.delay()` runs inline; patch `run_ai_on_message` (mirror `apps/triggers/tests` which patch `apps.<caller>.<module>.run_ai_on_message`) + `synthesize`.

---

## Task 1: `WarRoomRun` "running" status + voice-assignment helper

**Files:** `backend/apps/warroom/models.py` (+`running` choice, migration), `backend/apps/warroom/services/voices.py`, `tests/test_voices.py`.

- [ ] **Step 1: failing test** `backend/apps/warroom/tests/test_voices.py`:
```python
import pytest

from apps.warroom.services.voices import assign_voices

pytestmark = pytest.mark.django_db


def test_single_mode_all_default(monkeypatch):
    monkeypatch.setattr("apps.warroom.services.voices._enabled_providers", lambda: [("claude", "claude-opus-4-8")])
    out = assign_voices("single")
    assert {p for _persona, p, _m in out} == {"claude"}
    assert [persona for persona, _p, _m in out] == ["bull", "bear", "skeptic"]


def test_multi_mode_spreads_across_providers(monkeypatch):
    monkeypatch.setattr("apps.warroom.services.voices._enabled_providers",
                        lambda: [("claude", "claude-opus-4-8"), ("openai", "gpt-5")])
    out = assign_voices("multi")
    provs = [p for _persona, p, _m in out]
    assert provs[0] != provs[1] or len(set(provs)) > 1  # spread, not all-same


def test_multi_with_one_provider_falls_back(monkeypatch):
    monkeypatch.setattr("apps.warroom.services.voices._enabled_providers", lambda: [("claude", "claude-opus-4-8")])
    out = assign_voices("multi")
    assert {p for _persona, p, _m in out} == {"claude"}  # only one available -> all claude
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/warroom/services/voices.py`:
```python
"""Assign debate personas to providers per voice_mode. Multi-provider diversity
when >1 provider is enabled+configured, else everyone on the default."""

from __future__ import annotations

from apps.warroom import constants as C


def _enabled_providers() -> list[tuple[str, str]]:
    """[(provider, default_model), ...] for enabled providers that have a model."""
    from apps.secrets.models import ProviderConfig

    out = []
    for cfg in ProviderConfig.objects.filter(enabled=True):
        model = cfg.default_model or ""
        if model:
            out.append((cfg.provider, model))
    return out


def assign_voices(voice_mode: str) -> list[tuple[str, str, str]]:
    """Return [(persona, provider, model), ...] for bull/bear/skeptic."""
    providers = _enabled_providers()
    if not providers:
        # No configured provider — caller (run_debate) will mark the run errored.
        return [(p, "", "") for p in C.PERSONAS]
    if voice_mode != "multi" or len(providers) == 1:
        prov, model = providers[0]
        return [(p, prov, model) for p in C.PERSONAS]
    # multi: round-robin across providers for genuine diversity
    out = []
    for i, persona in enumerate(C.PERSONAS):
        prov, model = providers[i % len(providers)]
        out.append((persona, prov, model))
    return out
```

- [ ] **Step 4:** add `("running", "Running")` to `WarRoomRun.STATUS_CHOICES` in `models.py`; `makemigrations warroom` (`-u 1000:1000`, `dan`-owned).
- [ ] **Step 5:** run → PASS.
- [ ] **Step 6:** commit `feat(warroom): voice-assignment helper + running status (M15 F3 v2)`.

---

## Task 2: Persona execution helper

**Files:** `backend/apps/warroom/services/debate.py` (new), `tests/test_debate_persona.py`.

- [ ] **Step 1: failing test** `backend/apps/warroom/tests/test_debate_persona.py`:
```python
import pytest

from apps.threads.models import Message, Thread
from apps.warroom.services import debate as D

pytestmark = pytest.mark.django_db


def test_run_one_persona_dispatches_and_stamps(monkeypatch):
    th = Thread.objects.create(kind="warroom", title="t")
    captured = {}

    def _fake_run(**kw):
        captured.update(kw)
        Message.objects.create(thread_id=kw["thread_id"], role="assistant", status="done",
                               content={"text": "bull case", "kind": "investigation"})
        return {"status": "done"}

    monkeypatch.setattr(D, "run_ai_on_message", _fake_run)
    arg = D.run_one_persona(th, "bull", "SUBJECT ctx", [], provider="claude", model="claude-opus-4-8", grounding=True)
    assert arg["persona"] == "bull"
    assert "bull case" in arg["argument"]
    # provider routed via override; tools via investigate
    assert captured["override"] == {"provider": "claude", "model": "claude-opus-4-8"}
    assert captured["investigate"] is True
    # the assistant message is stamped with the persona for the courtroom UI
    msg = Message.objects.filter(thread=th, role="assistant").latest("created_at")
    assert msg.content["persona"] == "bull"
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** `backend/apps/warroom/services/debate.py`:
```python
"""Run a single persona as a real streaming run via run_ai_on_message (multi-
provider via override, tool-grounded via investigate), then stamp the persona on
the resulting assistant message so the courtroom UI can lane it."""

from __future__ import annotations

import logging

from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message
from apps.warroom.services.personas import _FRAMING, _user_prompt

log = logging.getLogger(__name__)


def run_one_persona(thread: Thread, persona: str, subject_context: str, prior_args: list[dict],
                    *, provider: str, model: str, grounding: bool) -> dict | None:
    """Returns {"persona", "argument"} or None if the run produced nothing."""
    # Persona framing lives in the USER turn (no system-prompt surgery needed).
    user_text = f"{_FRAMING[persona]}\n\n{_user_prompt(subject_context, prior_args)}"
    um = Message.objects.create(thread=thread, role="user", status="done", content={"text": user_text})
    override = {"provider": provider, "model": model} if provider and model else None
    try:
        run_ai_on_message(thread_id=thread.id, user_message_id=um.id, override=override, investigate=grounding)
    except Exception:
        log.warning("warroom.persona_run_failed persona=%s", persona, exc_info=True)
    assistant = Message.objects.filter(thread=thread, role="assistant", status="done").order_by("-created_at").first()
    if assistant is None:
        return None
    content = assistant.content if isinstance(assistant.content, dict) else {}
    argument = (content.get("text") or "").strip()
    if not argument:
        return None
    # stamp the persona so the courtroom UI can column it
    content["persona"] = persona
    assistant.content = content
    assistant.save(update_fields=["content"])
    return {"persona": persona, "argument": argument}
```
(Reuses `_FRAMING` + `_user_prompt` from v1 `personas.py` — keep those exported.)

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(warroom): streaming persona run (multi-provider + tool-grounded) (M15 F3 v2)`.

---

## Task 3: `run_debate` task + async `convene`

**Files:** `backend/apps/warroom/tasks.py` (new), `backend/apps/warroom/services/convene.py` (rewrite to dispatch), `config/celery.py` (autodiscover `apps.warroom`), `tests/test_run_debate.py`, update `tests/test_convene.py`.

- [ ] **Step 1: failing test** `backend/apps/warroom/tests/test_run_debate.py`:
```python
import pytest

from apps.threads.models import Message
from apps.warroom.models import WarRoomRun
from apps.warroom.services import convene as CV
from apps.warroom import tasks as T

pytestmark = pytest.mark.django_db


def _patch(monkeypatch):
    monkeypatch.setattr(T, "assign_voices", lambda mode: [(p, "claude", "claude-opus-4-8") for p in ("bull", "bear", "skeptic")])
    monkeypatch.setattr(T, "run_one_persona", lambda thread, persona, ctx, prior, **kw: {"persona": persona, "argument": f"{persona} arg"})

    class _V:
        verdict = "balanced"; confidence = 0.5; strongest_bull = "b"; strongest_bear = "r"; what_would_change_my_mind = "x"

    monkeypatch.setattr(T, "synthesize", lambda ctx, args, **kw: _V())
    monkeypatch.setattr(T, "_claude_cfg", lambda: ("k", "claude-opus-4-8", ""))


def test_convene_dispatches_running_run(monkeypatch):
    _patch(monkeypatch)
    run = CV.convene(free_prompt="NVDA?", structure="rebuttal", voice_mode="single")
    # CELERY eager -> run_debate already executed; run is now done
    run.refresh_from_db()
    assert run.status == "done"
    assert run.verdict["verdict"] == "balanced"
    assert Message.objects.filter(thread=run.thread, content__kind="warroom_verdict").exists()


def test_run_debate_no_provider_errors(monkeypatch):
    monkeypatch.setattr(T, "_claude_cfg", lambda: None)
    monkeypatch.setattr(T, "assign_voices", lambda mode: [(p, "", "") for p in ("bull", "bear", "skeptic")])
    run = CV.convene(free_prompt="q")
    run.refresh_from_db()
    assert run.status == "error"
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3a:** `backend/apps/warroom/tasks.py`:
```python
from __future__ import annotations

import logging

from celery import shared_task

from apps.threads.models import Message
from apps.warroom.models import WarRoomRun
from apps.warroom.services.convene import _claude_cfg
from apps.warroom.services.debate import run_one_persona
from apps.warroom.services.subject import subject_context
from apps.warroom.services.verdict import synthesize
from apps.warroom.services.voices import assign_voices
from apps.warroom import constants as C

log = logging.getLogger(__name__)


@shared_task(name="warroom.run_debate")
def run_debate(run_id: int) -> None:
    run = WarRoomRun.objects.filter(id=run_id).first()
    if run is None:
        return
    label, ctx = subject_context(
        thesis=run.thesis, coverage_note=run.coverage_note,
        book_snapshot=run.book_snapshot, free_prompt=run.free_prompt,
    )
    voices = assign_voices(run.params.get("voice_mode", "single"))
    if all(not prov for _p, prov, _m in voices):
        run.status = "error"; run.error = "No enabled provider configured."
        run.save(update_fields=["status", "error"]); return

    grounding = bool(run.params.get("grounding", True))
    structure = run.params.get("structure", C.DEFAULT_STRUCTURE)
    rounds = C.DEEP_MAX_ROUNDS if structure == "deep" else (1 if structure == "rebuttal" else 0)

    persona_args: list[dict] = []
    for r in range(rounds + 1):
        prior = list(persona_args) if r > 0 else []
        round_args = []
        for persona, provider, model in voices:
            arg = run_one_persona(run.thread, persona, ctx, prior, provider=provider, model=model, grounding=grounding)
            if arg:
                round_args.append(arg)
        if round_args:
            persona_args = round_args

    cfg = _claude_cfg()
    if cfg is None or not persona_args:
        run.status = "error"; run.error = "Debate produced no arguments / no Claude key for synthesis."
        run.save(update_fields=["status", "error"]); return
    api_key, model, base_url = cfg
    v = synthesize(ctx, persona_args, api_key=api_key, model=model, base_url=base_url)
    verdict = {"verdict": v.verdict, "confidence": v.confidence, "strongest_bull": v.strongest_bull,
               "strongest_bear": v.strongest_bear, "what_would_change_my_mind": v.what_would_change_my_mind}
    Message.objects.create(thread=run.thread, role="assistant", status="done",
                           content={"kind": "warroom_verdict", **verdict})
    run.verdict = verdict; run.confidence = v.confidence; run.status = "done"
    run.save(update_fields=["verdict", "confidence", "status"])
```

- [ ] **Step 3b:** REWRITE `backend/apps/warroom/services/convene.py` — keep `_claude_cfg()` (unchanged); replace `convene()` body so it only creates the run + thread (status `running`) + dispatches:
```python
def convene(*, thesis=None, coverage_note=None, book_snapshot=None, free_prompt="",
            structure=C.DEFAULT_STRUCTURE, voice_mode="single", grounding=True) -> WarRoomRun:
    from apps.threads.models import Thread
    from apps.warroom.tasks import run_debate

    label, _ctx = subject_context(thesis=thesis, coverage_note=coverage_note,
                                  book_snapshot=book_snapshot, free_prompt=free_prompt)
    subject_kind = ("thesis" if thesis else "coverage" if coverage_note else "book" if book_snapshot else "free")
    thread = Thread.objects.create(kind="warroom", title=f"Debate: {label}"[:200])
    run = WarRoomRun.objects.create(
        thread=thread, subject_kind=subject_kind, subject_label=label,
        thesis=thesis, coverage_note=coverage_note, book_snapshot=book_snapshot,
        free_prompt=free_prompt, params={"structure": structure, "voice_mode": voice_mode, "grounding": grounding},
        status="running",
    )
    run_debate.delay(run.id)  # CELERY eager in tests -> runs inline
    return run
```
Delete the old synchronous persona/verdict logic from `convene.py` (it now lives in `tasks.run_debate`). Keep `personas.py`/`verdict.py`/`subject.py` (still used). Update `tests/test_convene.py`: the old assertions about message counts move to `test_run_debate.py`; `test_convene` now just asserts a run is created + (eager) ends `done`.

- [ ] **Step 3c:** add `"apps.warroom",` to `autodiscover_tasks([...])` in `config/celery.py`.

- [ ] **Step 4:** run → PASS; then `pytest apps/warroom -q` (full regression — fix any v1 convene tests that assumed the old synchronous shape).
- [ ] **Step 5:** restart note: `docker compose restart worker beat` would be needed on a live stack for the new task; not needed in the test stack. commit `feat(warroom): async run_debate task + streaming multi-provider convene (M15 F3 v2)`.

---

## Task 4: API surfaces run status + the convene params

**Files:** `backend/apps/warroom/serializers.py` (already has `status`; ensure `params` exposed — it is), `tests/test_views_v2.py`.

- [ ] **Step 1: failing test** `backend/apps/warroom/tests/test_views_v2.py`:
```python
import pytest
from rest_framework.test import APIClient

from apps.warroom import views

pytestmark = pytest.mark.django_db


def test_convene_passes_v2_params(monkeypatch):
    captured = {}

    def _fake(**kw):
        captured.update(kw)
        from apps.threads.models import Thread
        from apps.warroom.models import WarRoomRun
        th = Thread.objects.create(kind="warroom", title="t")
        return WarRoomRun.objects.create(thread=th, subject_kind="free", subject_label="q", status="running")

    monkeypatch.setattr(views, "convene", _fake)
    resp = APIClient().post("/api/warroom/runs/convene/",
                            {"free_prompt": "q", "voice_mode": "multi", "grounding": True}, format="json")
    assert resp.status_code == 200
    assert captured["voice_mode"] == "multi"
    assert captured["grounding"] is True
    assert resp.json()["status"] == "running"
```

- [ ] **Step 2:** run → FAIL (v1 view hardcodes/ignores voice_mode? it passes them through — verify it forwards `voice_mode`/`grounding`). If the v1 `convene` action already forwards `voice_mode`/`grounding` (it does, per the v1 plan), this may pass once the serializer exposes `status` (it does). Adjust the view if needed so `voice_mode`/`grounding` are forwarded from `request.data`.

- [ ] **Step 3:** ensure `WarRoomViewSet.convene` forwards `voice_mode=d.get("voice_mode","single")` + `grounding=bool(d.get("grounding", True))` (the v1 view already does; confirm).

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(warroom): convene API forwards voice_mode + grounding (M15 F3 v2)`.

---

## Task 5: Frontend — convene controls (voice mode + grounding)

**Files:** `frontend/src/api/warroom.ts` (+`voice_mode`/`grounding` in `ConveneBody`), `frontend/src/pages/WarRoomPage.tsx`, `frontend/src/__tests__/WarRoomPage.v2.test.tsx`.

- [ ] **Step 1:** add to `ConveneBody`: `voice_mode?: "single" | "multi"; grounding?: boolean;`.

- [ ] **Step 2: failing test** `frontend/src/__tests__/WarRoomPage.v2.test.tsx` — render the page, assert a "Multi-provider" control + a "Grounded" toggle are present (e.g. `screen.getByLabelText(/multi-provider|grounded/i)` or by text). Keep it light (presence of the controls).

- [ ] **Step 3:** in `WarRoomPage.tsx` add a `voice_mode` select (single/multi) + a `grounding` checkbox to the convene form; pass them in `convene.mutateAsync({ free_prompt, structure, voice_mode, grounding })`.

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(warroom): convene form voice-mode + grounding controls (M15 F3 v2)`.

---

## Task 6: Frontend — live-streaming courtroom

**Files:** `frontend/src/pages/WarRoomDetailPage.tsx` (or extend WarRoomPage with a selected-run view), router, test.

The debate now streams into the `warroom` thread. A run detail view subscribes to that thread over WS (reuse the existing `WebSocketProvider` + a `useLiveMessages`-style hook keyed on `thread_id`) and renders persona-laned columns (group the run's `messages` by `content.persona`), the running status, and the verdict card when `status === "done"`.

- [ ] **Step 1: failing test** `frontend/src/__tests__/WarRoomDetail.test.tsx` — mock `apiGet` for `/api/warroom/runs/:id/` returning a run with persona-tagged `messages` + a verdict; assert bull/bear/skeptic columns + the verdict render. (Live WS is exercised by existing WS infra; this test covers the static render of a completed run.)

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3:** implement `WarRoomDetailPage` (or a `<RunDetail>` in WarRoomPage): fetch the run; group `messages.filter(m => m.content.persona)` into columns by persona; show `verdict` card; if `status === "running"`, subscribe to the warroom thread WS (existing provider) to append streaming text live. Add a route `warroom/:id` (crumb "Debate"). Link each past-debate row on `/warroom` to it.

- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** commit `feat(warroom): live-streaming courtroom run view (M15 F3 v2)`.

---

## Final verification (F3 v2)
- `pytest apps/warroom apps/threads -q` (convene now drives run_ai_on_message via run_debate)
- ruff check + format on apps/warroom
- Frontend vitest: warroom test files (v1 + v2)
- **Live-stack note:** `docker compose restart worker beat` to register `warroom.run_debate` on a running stack (worker/beat don't hot-reload).

## Self-review
- Multi-provider voices (override per persona) → Tasks 1, 2, 3. ✓
- Tool-grounding (investigate=True → M14 loop) → Task 2. ✓
- Live streaming (async run_debate into the warroom thread + WS courtroom) → Tasks 3, 6. ✓
- Structure-as-choice preserved (rounds in run_debate) → Task 3. ✓
- Synthesizer verdict unchanged (`run_structured`) → Task 3. ✓
- **Risk flags:** persona framing in the user turn (avoids system-prompt surgery); `investigate=True` reused for tools means persona assistant messages are tagged `kind:"investigation"` then re-stamped `persona` — verify nothing downstream keys off `kind=="investigation"` for warroom threads (it shouldn't; observer/analytics filter by thread kind). Confirm `_FRAMING`/`_user_prompt` are importable from `personas.py`.
