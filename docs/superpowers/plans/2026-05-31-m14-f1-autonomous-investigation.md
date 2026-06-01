# M14 F1 — Autonomous Investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a trigger or observer schedule fires with `investigate=True`, the AI runs a **bounded** tool-using investigation (pull data, follow leads, conclude) instead of a single tool-less observation — reusing the existing chat run path as a mode, not a new pipeline.

**Architecture:** Add `max_tool_iterations` to `RunRequest`; enforce it in both providers' `while True` tool loops (after N rounds, drop tools so the model must conclude). Add an `investigate` mode to `run_ai_on_message` that forces the toolset on, sets the iteration cap, appends an investigation directive to the system prompt, gates on a dedicated autonomous daily cap, and tags the assistant message `kind="investigation"`. Opt-in per trigger/schedule via a new boolean field.

**Tech Stack:** Django 5 / DRF, Celery, anthropic + openai SDKs, pytest (container: `docker compose exec web pytest <path>` — drop the `backend/` prefix; WORKDIR is `/app/backend`).

---

### Task 1: `RunRequest.max_tool_iterations`

**Files:**
- Modify: `backend/apps/ai/types.py` (the `RunRequest` dataclass, ~line 19-30)
- Test: `backend/apps/ai/tests/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/ai/tests/test_types.py  (append; create file if absent)
from apps.ai.types import RunRequest


def test_run_request_max_tool_iterations_defaults_to_unlimited():
    req = RunRequest(model="m", system="s", messages=[])
    assert req.max_tool_iterations == 0  # 0 = unlimited (chat default, behavior unchanged)
```

- [ ] **Step 2: Run it (fails — no such field)**

Run: `docker compose exec web pytest apps/ai/tests/test_types.py -v`
Expected: FAIL (`AttributeError` / `TypeError`).

- [ ] **Step 3: Add the field**

In `RunRequest`, after `memory_dir: str = ""`:

```python
    max_tool_iterations: int = 0  # 0 = unlimited tool rounds (chat default); >0 bounds autonomous runs
```

- [ ] **Step 4: Run it (passes).** `docker compose exec web pytest apps/ai/tests/test_types.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/ai/types.py backend/apps/ai/tests/test_types.py
git commit -m "feat(ai): add RunRequest.max_tool_iterations (bounded tool loop)"
```

---

### Task 2: Enforce the cap in the Claude provider loop

**Files:**
- Modify: `backend/apps/ai/providers/claude.py` (the `while True` loop, ~line 52-142)
- Test: `backend/apps/ai/tests/test_provider_tool_cap.py` (new)

- [ ] **Step 1: Write the failing test** (stubs the SDK stream; asserts exactly N tool rounds when the model keeps asking for tools)

```python
# backend/apps/ai/tests/test_provider_tool_cap.py
import pytest

from apps.ai.providers.claude import ClaudeProvider
from apps.ai.types import RunRequest, ToolCallEvent


class _Block:
    type = "tool_use"
    id = "tu_1"
    name = "get_quote"
    input = {"ticker": "NVDA"}


class _Usage:
    input_tokens = 1
    output_tokens = 1
    cache_read_input_tokens = 0


class _Final:
    stop_reason = "tool_use"  # model ALWAYS wants another tool round
    usage = _Usage()
    content = [_Block()]


class _FakeStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def __aiter__(self):
        if False:  # no text events needed for this test
            yield None

    async def get_final_message(self):
        return _Final()


@pytest.mark.asyncio
async def test_claude_caps_tool_rounds(monkeypatch):
    provider = ClaudeProvider(api_key="k")

    monkeypatch.setattr(provider._client.messages, "stream", lambda **kw: _FakeStream())

    class _FakeToolset:
        def run(self, name, inp):
            return {"ok": True, "result": "42"}

    monkeypatch.setattr("apps.ai.providers.claude._resolve_toolset", lambda: _FakeToolset())

    req = RunRequest(
        model="claude-x",
        system="s",
        messages=[],
        tools=[{"name": "get_quote", "input_schema": {"type": "object"}}],
        max_tool_iterations=2,
    )
    tool_calls = [e async for e in provider.run(req) if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 2  # bounded: 2 rounds, then a tool-less concluding turn
```

- [ ] **Step 2: Run it (fails — loop is unbounded, hangs/exceeds).**

Run: `docker compose exec web pytest apps/ai/tests/test_provider_tool_cap.py::test_claude_caps_tool_rounds -v`
Expected: FAIL (the unbounded loop never stops → the test would loop; if it returns, count != 2).

- [ ] **Step 3: Add the cap.** Replace the loop preamble + tail. Before `while True:` introduce the counters; compute `tools_list` from `tools_enabled`; after appending tool results, increment and flip.

Restructure the loop head so `tools_list` is computed first:

```python
        total_in = total_out = total_cached = 0
        memory_handler = _make_memory_handler(req.memory_dir)
        tool_rounds = 0
        tools_enabled = True

        try:
            while True:
                tools_list: list[dict] = list(req.tools) if tools_enabled else []
                if req.memory_dir and tools_enabled:
                    tools_list.append({"type": "memory_20250818", "name": "memory"})
                stream_kwargs: dict = dict(
                    model=req.model,
                    system=system_blocks,
                    messages=messages,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                )
                if tools_list:
                    stream_kwargs["tools"] = tools_list
                if req.thinking_budget > 0:
                    stream_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": req.thinking_budget,
                    }
                # ... (stream_ctx / async with / final unchanged) ...
```

Then after the existing `messages.append({"role": "user", "content": tool_results})` line, add:

```python
                tool_rounds += 1
                if req.max_tool_iterations and tool_rounds >= req.max_tool_iterations:
                    # Hit the ceiling: next pass runs tool-less so the model concludes
                    # (the `not tools_list` guard then breaks the loop).
                    tools_enabled = False
```

(Delete the old `tools_list: list[dict] = list(req.tools)` / `if req.memory_dir:` / `if tools_list:` block that previously sat *after* `stream_kwargs` — it's now computed before `stream_kwargs`.)

- [ ] **Step 4: Run it (passes).** `docker compose exec web pytest apps/ai/tests/test_provider_tool_cap.py::test_claude_caps_tool_rounds -v`

- [ ] **Step 5: Regression — existing claude provider tests still pass.**

Run: `docker compose exec web pytest apps/ai/tests/ -k claude -v`
Expected: PASS (unbounded default `max_tool_iterations=0` leaves chat unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/ai/providers/claude.py backend/apps/ai/tests/test_provider_tool_cap.py
git commit -m "feat(ai): bound the Claude tool loop by max_tool_iterations"
```

---

### Task 3: Enforce the cap in the OpenAI/Local provider loop

**Files:**
- Modify: `backend/apps/ai/providers/openai.py` (the `while True` loop, ~line 65-166)
- Test: `backend/apps/ai/tests/test_provider_tool_cap.py` (append)

- [ ] **Step 1: Write the failing test**

```python
# append to backend/apps/ai/tests/test_provider_tool_cap.py
from apps.ai.providers.openai import OpenAIProvider


class _Delta:
    def __init__(self):
        self.content = None
        self.tool_calls = [
            type("TC", (), {
                "index": 0,
                "id": "tc1",
                "function": type("F", (), {"name": "get_quote", "arguments": '{"ticker":"NVDA"}'})(),
            })()
        ]


class _Choice:
    def __init__(self):
        self.delta = _Delta()
        self.finish_reason = "tool_calls"  # always wants another round


class _Chunk:
    def __init__(self):
        self.choices = [_Choice()]
        self.usage = None


async def _fake_create(**kw):
    async def gen():
        yield _Chunk()
    return gen()


@pytest.mark.asyncio
async def test_openai_caps_tool_rounds(monkeypatch):
    provider = OpenAIProvider(api_key="k")
    monkeypatch.setattr(provider._client.chat.completions, "create", _fake_create)
    monkeypatch.setattr("apps.ai.providers.openai._resolve_toolset",
                        lambda: type("TS", (), {"run": lambda self, n, i: {"ok": True, "result": "42"}})())
    req = RunRequest(model="gpt-x", system="s", messages=[],
                     tools=[{"type": "function", "function": {"name": "get_quote"}}],
                     max_tool_iterations=2)
    tool_calls = [e async for e in provider.run(req) if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 2
```

- [ ] **Step 2: Run it (fails).** `docker compose exec web pytest apps/ai/tests/test_provider_tool_cap.py::test_openai_caps_tool_rounds -v`

- [ ] **Step 3: Add the cap.** Before `while True:` add `tool_rounds = 0` and `tools_enabled = True`. Change the tools line to:

```python
                if req.tools and tools_enabled:
                    create_kwargs["tools"] = req.tools
```

After the `for s in ordered:` dispatch loop completes (just before the `while` repeats), add:

```python
                tool_rounds += 1
                if req.max_tool_iterations and tool_rounds >= req.max_tool_iterations:
                    tools_enabled = False
```

- [ ] **Step 4: Run it (passes).** Same command.
- [ ] **Step 5: Regression.** `docker compose exec web pytest apps/ai/tests/ -k openai -v`
- [ ] **Step 6: Commit**

```bash
git add backend/apps/ai/providers/openai.py backend/apps/ai/tests/test_provider_tool_cap.py
git commit -m "feat(ai): bound the OpenAI/local tool loop by max_tool_iterations"
```

---

### Task 4: Autonomous settings + investigation mode helper

**Files:**
- Modify: `backend/config/settings/base.py` (near line 211, by the AI_FAILOVER block)
- Modify: `backend/apps/threads/tasks.py` (add `_INVESTIGATION_DIRECTIVE` + `_apply_investigation_mode`)
- Test: `backend/apps/threads/tests/test_investigation_mode.py` (new)

- [ ] **Step 1: Add settings.** After `AI_FAILOVER_PROVIDER = ...`:

```python
# Autonomous investigation (M14 F1): bounded tool-using runs on trigger/observer fires.
AI_INVESTIGATION_MAX_ITERATIONS = env.int("AI_INVESTIGATION_MAX_ITERATIONS", default=8)
# Separate, lower daily ceiling that GATES autonomous runs (0 = no separate gate; the
# provider's own daily cap still applies). Checked against total provider spend today.
AI_AUTONOMOUS_DAILY_CAP_USD = env.float("AI_AUTONOMOUS_DAILY_CAP_USD", default=0.0)
```

- [ ] **Step 2: Write the failing test**

```python
# backend/apps/threads/tests/test_investigation_mode.py
from apps.ai.types import RunRequest
from apps.threads.tasks import _apply_investigation_mode


class _Cfg:
    supports_tools = True


def test_apply_investigation_mode_forces_tools_cap_and_directive(settings):
    settings.AI_INVESTIGATION_MAX_ITERATIONS = 5
    req = RunRequest(model="m", system="Base.", messages=[], tools=[])
    _apply_investigation_mode(req, provider_name="claude", cfg=_Cfg())
    assert req.max_tool_iterations == 5
    assert req.tools, "claude investigation must force the toolset on"
    assert "What I checked" in req.system and "What to watch" in req.system
```

- [ ] **Step 3: Run it (fails — no `_apply_investigation_mode`).**

Run: `docker compose exec web pytest apps/threads/tests/test_investigation_mode.py -v`

- [ ] **Step 4: Implement.** In `backend/apps/threads/tasks.py`, after the imports/constants near the top (after `_PARTIAL_FLUSH_SECONDS`):

```python
_INVESTIGATION_DIRECTIVE = (
    "## Investigation mode\n"
    "You are running autonomously with tools and no human watching. Do not answer "
    "from the given snapshot alone — INVESTIGATE: use your tools to pull what you "
    "need (intraday prices, news, the option chain, your own past calls on this "
    "name), follow the leads they open, and cross-check before you commit to a read. "
    "You have a limited number of tool rounds; spend them, then write ONE conclusion "
    "with exactly these sections:\n"
    "**What I checked** — the tools/data you pulled and why.\n"
    "**What I found** — the concrete findings, each tied to a tool result.\n"
    "**What it means** — your read, with confidence and what would invalidate it.\n"
    "**What to watch** — the specific levels/events that would change the picture."
)


def _apply_investigation_mode(req, *, provider_name: str, cfg) -> None:
    """Turn a normal RunRequest into a bounded autonomous investigation: force the
    toolset on (when the provider can run tools), cap the tool rounds, and append
    the investigation directive to the system prompt. Mutates `req` in place."""
    from django.conf import settings

    req.max_tool_iterations = int(getattr(settings, "AI_INVESTIGATION_MAX_ITERATIONS", 8))
    if provider_name == "claude" or getattr(cfg, "supports_tools", False):
        from apps.ai.tools.registry import default_toolset

        ts = default_toolset()
        req.tools = ts.anthropic_tools() if provider_name == "claude" else ts.openai_tools()
    req.system = f"{req.system}\n\n{_INVESTIGATION_DIRECTIVE}"
```

- [ ] **Step 5: Run it (passes).** Same command.
- [ ] **Step 6: Commit**

```bash
git add backend/config/settings/base.py backend/apps/threads/tasks.py backend/apps/threads/tests/test_investigation_mode.py
git commit -m "feat(threads): investigation-mode helper + autonomous run settings"
```

---

### Task 5: Wire `investigate` through `run_ai_on_message`

**Files:**
- Modify: `backend/apps/threads/tasks.py` (`run_ai_on_message`, `_run_ai_on_message`, `_resolve_run_config`)
- Test: `backend/apps/threads/tests/test_investigation_mode.py` (append)

- [ ] **Step 1: Write the failing test** (autonomous cap gate blocks the run when total spend is over the autonomous ceiling)

```python
# append to test_investigation_mode.py
import pytest
from apps.ai.cost import CostCapExceededError
from apps.threads import tasks as thr_tasks


@pytest.mark.django_db
def test_investigation_gated_by_autonomous_cap(settings, monkeypatch):
    settings.AI_AUTONOMOUS_DAILY_CAP_USD = 1.0
    calls = {"autonomous_checked": False}

    def _fake_daily(provider, *, cap_usd):
        # The autonomous gate passes cap_usd == Decimal("1.0"); raise on it.
        from decimal import Decimal
        if cap_usd == Decimal("1.0"):
            calls["autonomous_checked"] = True
            raise CostCapExceededError("autonomous daily cap hit")

    monkeypatch.setattr(thr_tasks, "check_daily_cap", _fake_daily)
    monkeypatch.setattr(thr_tasks, "check_monthly_cap", lambda *a, **k: None)
    # _resolve_run_config needs a thread+provider; build minimal rows.
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig
    from apps.threads.models import Message, Thread

    ProviderConfig.objects.create(provider="claude", enabled=True, default_model="claude-opus-4-8")
    prof = TradingProfile.objects.create(name="p", default_provider="claude", default_model="claude-opus-4-8")
    thread = Thread.objects.create(kind="chat", profile=prof)
    user = Message.objects.create(thread=thread, role="user", content={"text": "hi"}, status="done")

    out = thr_tasks._resolve_run_config(
        thread=thread, user_msg=user, override=None, parent_message_id=None, investigate=True
    )
    assert calls["autonomous_checked"]
    assert isinstance(out, dict) and out["error"] == "cost_capped"
```

- [ ] **Step 2: Run it (fails — `_resolve_run_config` has no `investigate` param).**

Run: `docker compose exec web pytest apps/threads/tests/test_investigation_mode.py::test_investigation_gated_by_autonomous_cap -v`

- [ ] **Step 3: Implement.** Three edits in `tasks.py`:

(a) `run_ai_on_message` signature + passthrough — add `investigate: bool = False` to the `@shared_task` params and to the `_run_ai_on_message(...)` call inside it.

(b) `_resolve_run_config` — add `investigate: bool = False` to the signature, and after the existing daily/monthly cap block (inside the same `try`), add the autonomous gate:

```python
    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd)
        if investigate:
            from decimal import Decimal as _D

            from django.conf import settings as _s

            auto_cap = float(getattr(_s, "AI_AUTONOMOUS_DAILY_CAP_USD", 0.0) or 0.0)
            if auto_cap > 0:
                check_daily_cap(provider_name, cap_usd=_D(str(auto_cap)))
    except CostCapExceededError as exc:
        ...  # (unchanged failure block)
```

(c) `_run_ai_on_message` — add `investigate: bool = False` to the signature; pass `investigate=investigate` into `_resolve_run_config(...)`; after `req.model = model_id`, add:

```python
    if investigate:
        _apply_investigation_mode(req, provider_name=provider_name, cfg=cfg)
```

and change the assistant-message creation `content={"text": ""}` to:

```python
        content={"text": "", "kind": "investigation"} if investigate else {"text": ""},
```

- [ ] **Step 4: Run it (passes).** Same command.
- [ ] **Step 5: Regression — the chat path is unchanged.**

Run: `docker compose exec web pytest apps/threads/tests/ -k "run_ai or tasks" -v`
Expected: PASS (default `investigate=False` is a no-op).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/threads/tasks.py backend/apps/threads/tests/test_investigation_mode.py
git commit -m "feat(threads): investigate mode on run_ai_on_message (cap-gated, tagged)"
```

---

### Task 6: Trigger opt-in field + dispatch

**Files:**
- Modify: `backend/apps/triggers/models.py` (add field), new migration
- Modify: `backend/apps/triggers/tasks.py` (`_do_fire`, ~line 195)
- Test: `backend/apps/triggers/tests/test_fire_investigate.py` (new)

- [ ] **Step 1: Add the field.** In `EventTrigger`, after `enabled = models.BooleanField(default=True)`:

```python
    investigate = models.BooleanField(
        default=False,
        help_text="When True, a fire runs a bounded tool-using investigation "
        "instead of a single observation.",
    )
```

- [ ] **Step 2: Make the migration.**

Run: `docker compose exec web python manage.py makemigrations triggers`
Expected: a new `apps/triggers/migrations/00NN_eventtrigger_investigate.py` adding a `BooleanField(default=False)` (safe, non-locking on Postgres).

- [ ] **Step 3: Write the failing test**

```python
# backend/apps/triggers/tests/test_fire_investigate.py
import pytest
from apps.triggers import tasks as trig_tasks


@pytest.mark.django_db
def test_do_fire_passes_investigate_flag(monkeypatch):
    captured = {}

    class _Delay:
        def delay(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(trig_tasks, "run_ai_on_message", _Delay())
    # Stub capture + cost-cap + notify so the fire reaches the dispatch line.
    monkeypatch.setattr(trig_tasks, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(trig_tasks, "check_monthly_cap", lambda *a, **k: None)
    monkeypatch.setattr(trig_tasks, "notify", lambda **k: None)
    monkeypatch.setattr(trig_tasks, "serialize_for_ai", lambda *a, **k: "PAYLOAD")

    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig
    from apps.snapshots.models import Snapshot
    from apps.triggers.models import EventTrigger

    prof = TradingProfile.objects.create(name="p", default_provider="claude", default_model="claude-opus-4-8")
    ProviderConfig.objects.create(provider="claude", enabled=True, default_model="claude-opus-4-8")
    snap = Snapshot.objects.create(profile=prof, status="ready", objective="o")
    monkeypatch.setattr(trig_tasks, "capture", lambda **k: snap)
    monkeypatch.setattr("apps.threads.coach.assemble_coach_context", lambda *a, **k: "")

    trig = EventTrigger.objects.create(
        name="t", condition={"metric": "price", "ticker": "NVDA", "op": ">", "value": 1},
        profile=prof, enabled=True, investigate=True,
    )
    trig_tasks._do_fire(trigger_id=trig.id, matched_values={"price": 2})
    assert captured.get("investigate") is True
```

- [ ] **Step 4: Run it (fails — `_do_fire` doesn't pass `investigate`).**

Run: `docker compose exec web pytest apps/triggers/tests/test_fire_investigate.py -v`

- [ ] **Step 5: Implement.** In `_do_fire`, change the dispatch line to:

```python
    run_ai_on_message.delay(
        thread_id=thread.id, user_message_id=user_msg.id, investigate=trigger.investigate
    )
```

- [ ] **Step 6: Run it (passes).** Same command.
- [ ] **Step 7: Commit**

```bash
git add backend/apps/triggers/models.py backend/apps/triggers/migrations/ backend/apps/triggers/tasks.py backend/apps/triggers/tests/test_fire_investigate.py
git commit -m "feat(triggers): opt-in investigate flag dispatches a bounded investigation"
```

---

### Task 7: Observer opt-in field + dispatch (plain path)

**Files:**
- Modify: `backend/apps/observer/models.py` (add field), new migration
- Modify: `backend/apps/observer/services/run.py` (the plain `else` dispatch, ~line 150)
- Test: `backend/apps/observer/tests/test_run_investigate.py` (new)

- [ ] **Step 1: Add the field.** In `ObserverSchedule`, near `consensus`:

```python
    investigate = models.BooleanField(
        default=False,
        help_text="When True (plain mode only), the fire runs a bounded tool-using "
        "investigation instead of a single observation.",
    )
```

- [ ] **Step 2: Make the migration.** `docker compose exec web python manage.py makemigrations observer`

- [ ] **Step 3: Write the failing test**

```python
# backend/apps/observer/tests/test_run_investigate.py
import pytest
from apps.observer.services import run as obs_run


@pytest.mark.django_db
def test_plain_observer_passes_investigate_flag(monkeypatch):
    captured = {}
    monkeypatch.setattr(obs_run.run_ai_on_message, "delay", lambda **kw: captured.update(kw))
    monkeypatch.setattr(obs_run, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(obs_run, "check_monthly_cap", lambda *a, **k: None)
    monkeypatch.setattr(obs_run, "notify", lambda **k: None)
    monkeypatch.setattr(obs_run, "assemble_coach_context", lambda *a, **k: "")
    monkeypatch.setattr(obs_run, "serialize_for_ai", lambda *a, **k: "PAYLOAD")

    from apps.observer.models import ObserverSchedule
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig
    from apps.snapshots.models import Snapshot

    prof = TradingProfile.objects.create(name="p", default_provider="claude", default_model="claude-opus-4-8")
    ProviderConfig.objects.create(provider="claude", enabled=True, default_model="claude-opus-4-8")
    snap = Snapshot.objects.create(profile=prof, status="ready", objective="o")
    monkeypatch.setattr(obs_run, "capture", lambda **k: snap)
    sched = ObserverSchedule.objects.create(
        name="s", profile=prof, enabled=True, market_hours_only=False, investigate=True,
    )
    obs_run.run_observer(sched.id)
    assert captured.get("investigate") is True
```

- [ ] **Step 4: Run it (fails).** `docker compose exec web pytest apps/observer/tests/test_run_investigate.py -v`

- [ ] **Step 5: Implement.** In `run_observer`'s plain `else` branch, change the dispatch:

```python
            run_ai_on_message.delay(
                thread_id=thread.id,
                user_message_id=msg.id,
                override=override or None,
                investigate=sched.investigate,
            )
```

- [ ] **Step 6: Run it (passes).** Same command.
- [ ] **Step 7: Commit**

```bash
git add backend/apps/observer/models.py backend/apps/observer/migrations/ backend/apps/observer/services/run.py backend/apps/observer/tests/test_run_investigate.py
git commit -m "feat(observer): opt-in investigate flag on plain-mode fires"
```

---

### Task 8: Feature verification + conventions pass

- [ ] **Step 1: Full F1 test sweep.** `docker compose exec web pytest apps/ai/tests/test_provider_tool_cap.py apps/threads/tests/test_investigation_mode.py apps/triggers/tests/test_fire_investigate.py apps/observer/tests/test_run_investigate.py -v` → all PASS.
- [ ] **Step 2: Migrations check.** `docker compose exec web python manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Step 3: Lint.** `make lint` (ruff + eslint; `ty` advisory) → clean.
- [ ] **Step 4: Restart worker/beat** (they don't hot-reload task code): `docker compose restart worker beat`.
- [ ] **Step 5: Conventions check.** Run the `conventions-check` skill against the diff (Celery: no new task module — `run_investigation` is a mode on the registered `run_ai_on_message`, so nothing to register; section state untouched; caps respected; nothing bound to 0.0.0.0).

## Self-review notes
- **Spec coverage:** bounded loop (T1-3) ✓, force-tools + directive + cap-gate + message kind (T4-5) ✓, opt-in trigger/observer dispatch (T6-7) ✓, reply-to-alert is deferred to a follow-up (the fire thread already exists; enabling tools for its follow-up turns is a small `_resolve_capabilities` change — out of this plan's scope, tracked in the spec).
- **No new Celery module** — deliberately reused `run_ai_on_message` to avoid the autodiscover trap.
- **Notification kind** reused (no migration); the `Message.content["kind"]="investigation"` is the marker.
- **Cost:** autonomous gate is opt-in (`AI_AUTONOMOUS_DAILY_CAP_USD=0` → only the normal cap applies); iteration ceiling defaults to 8.
