# Provider Tool Parity + Capability Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend tool-calling to the OpenAI and local providers (opt-in via a new `ProviderConfig.supports_tools` flag) and surface a visible thread warning when a profile enables a feature the selected provider cannot honor.

**Architecture:** `Toolset` gains an `openai_tools()` serializer alongside the existing `anthropic_tools()`. `OpenAIProvider.run()` grows a tool-call loop that emits the *existing* `ToolCallEvent`/`ToolResultEvent` — so the already-provider-agnostic streaming loop in `apps/threads/tasks.py` needs no changes to handle them. A pure `unsupported_features()` helper drives a warn-and-continue `system` message + WS `warning` event. `LocalProvider` inherits everything from `OpenAIProvider`.

**Tech Stack:** Django, DRF, `openai` async SDK, pytest (`pytest.mark.asyncio`), `MagicMock`-based fake streams. Everything runs in Docker — backend tests via `docker compose exec web pytest ...`.

**Spec:** `docs/superpowers/specs/2026-05-26-provider-tool-parity-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/apps/ai/tools/__init__.py` | Tool serialization for both wire formats | Modify: add `Toolset.openai_tools()` |
| `backend/apps/ai/providers/openai.py` | OpenAI streaming + tool loop (LocalProvider inherits) | Modify: add tool loop |
| `backend/apps/ai/capabilities.py` | Pure "which enabled features can't this provider do" helper | Create |
| `backend/apps/secrets/models.py` | `supports_tools` field | Modify |
| `backend/apps/secrets/migrations/0004_providerconfig_supports_tools.py` | DB migration | Create |
| `backend/apps/secrets/serializers.py` | Expose `supports_tools` | Modify |
| `backend/apps/threads/tasks.py` | Gating in `_build_request`; warning emission in `run_ai_on_message` | Modify |
| `backend/apps/ai/tests/test_tool_registry.py` | `openai_tools()` shape test | Modify |
| `backend/apps/ai/tests/test_openai_provider.py` | Tool-loop tests | Modify |
| `backend/apps/ai/tests/test_capabilities.py` | `unsupported_features` truth table | Create |
| `backend/apps/threads/tests/test_run_ai_routing.py` | `_build_request` gating matrix | Modify |
| `backend/apps/threads/tests/test_run_ai.py` | Warning emission + dedupe | Modify |

**Test invocation note:** all `pytest` commands run inside the `web` container, e.g. `docker compose exec web pytest backend/apps/ai/tests/test_tool_registry.py -v`. If the stack isn't up, `make dev` first (or `docker compose up -d web db redis`).

---

## Task 1: `Toolset.openai_tools()` serializer

**Files:**
- Modify: `backend/apps/ai/tools/__init__.py` (add method after `anthropic_tools`, ~line 34)
- Test: `backend/apps/ai/tests/test_tool_registry.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/apps/ai/tests/test_tool_registry.py`:

```python
def test_openai_tools_shape():
    from apps.ai.tools import ToolSpec, Toolset

    ts = Toolset()
    ts.register(
        ToolSpec(
            name="get_quote",
            description="Get a quote.",
            input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}},
            fn=lambda **kw: kw,
        )
    )
    tools = ts.openai_tools()
    assert tools == [
        {
            "type": "function",
            "function": {
                "name": "get_quote",
                "description": "Get a quote.",
                "parameters": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                },
            },
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/ai/tests/test_tool_registry.py::test_openai_tools_shape -v`
Expected: FAIL with `AttributeError: 'Toolset' object has no attribute 'openai_tools'`

- [ ] **Step 3: Write minimal implementation**

In `backend/apps/ai/tools/__init__.py`, add immediately after the `anthropic_tools` method (after line 34):

```python
    def openai_tools(self) -> list[dict]:
        """Serialize specs to the shape OpenAI's tools= param expects."""
        return [
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.input_schema,
                },
            }
            for s in self.specs.values()
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/ai/tests/test_tool_registry.py::test_openai_tools_shape -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/ai/tools/__init__.py backend/apps/ai/tests/test_tool_registry.py
git commit -m "feat(ai): add Toolset.openai_tools() serializer"
```

---

## Task 2: OpenAI provider tool-call loop

**Files:**
- Modify: `backend/apps/ai/providers/openai.py` (rewrite `run()` body to loop; add `import json`)
- Test: `backend/apps/ai/tests/test_openai_provider.py`

The OpenAI SDK streams tool calls as `choice.delta.tool_calls` fragments carrying `index`, `id`, `function.name`, `function.arguments`. The `arguments` string arrives in pieces across deltas and must be accumulated by `index`, then `json.loads`'d once the stream finishes with `finish_reason == "tool_calls"`. After dispatching tools, the assistant `tool_calls` turn plus one `{"role": "tool", ...}` message per result are appended, and the request loops.

- [ ] **Step 1: Write the failing test**

Add to `backend/apps/ai/tests/test_openai_provider.py` (the file already imports `MagicMock`, `patch`, `pytest`, and provider/types):

```python
from apps.ai.types import ToolCallEvent, ToolResultEvent


class _FakeToolCallStream:
    """First round: stream a tool_call split across deltas, finish_reason=tool_calls."""

    def __aiter__(self):
        async def gen():
            # fragment 1: id + name, arguments start
            c1 = MagicMock()
            ch1 = MagicMock()
            ch1.delta.content = None
            tc1 = MagicMock()
            tc1.index = 0
            tc1.id = "call_1"
            tc1.function.name = "get_quote"
            tc1.function.arguments = '{"ti'
            ch1.delta.tool_calls = [tc1]
            ch1.finish_reason = None
            c1.choices = [ch1]
            c1.usage = None
            yield c1
            # fragment 2: more arguments, no id/name
            c2 = MagicMock()
            ch2 = MagicMock()
            ch2.delta.content = None
            tc2 = MagicMock()
            tc2.index = 0
            tc2.id = None
            tc2.function.name = None
            tc2.function.arguments = 'cker": "AAPL"}'
            ch2.delta.tool_calls = [tc2]
            ch2.finish_reason = "tool_calls"
            c2.choices = [ch2]
            c2.usage = MagicMock(
                prompt_tokens=50,
                completion_tokens=5,
                prompt_tokens_details=MagicMock(cached_tokens=0),
            )
            yield c2

        return gen()


class _FakeTextStream:
    """Second round: plain text answer, finish_reason=stop."""

    def __aiter__(self):
        async def gen():
            c = MagicMock()
            ch = MagicMock()
            ch.delta.content = "AAPL is at 200."
            ch.delta.tool_calls = None
            ch.finish_reason = "stop"
            c.choices = [ch]
            c.usage = MagicMock(
                prompt_tokens=70,
                completion_tokens=8,
                prompt_tokens_details=MagicMock(cached_tokens=0),
            )
            yield c

        return gen()


@pytest.mark.asyncio
async def test_openai_tool_loop_dispatches_and_continues():
    streams = [_FakeToolCallStream(), _FakeTextStream()]
    captured_calls = []
    fake = MagicMock()

    async def fake_create(**kwargs):
        captured_calls.append(kwargs)
        return streams.pop(0)

    fake.chat.completions.create = fake_create

    fake_toolset = MagicMock()
    fake_toolset.run.return_value = {"ok": True, "result": {"last": 200}}

    with (
        patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake),
        patch("apps.ai.providers.openai._resolve_toolset", return_value=fake_toolset),
    ):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="You help.",
            messages=[ChatMessage(role="user", content="quote AAPL")],
            tools=[{"type": "function", "function": {"name": "get_quote",
                    "description": "", "parameters": {}}}],
        )
        events = [evt async for evt in provider.run(req)]

    # tool dispatched with the accumulated + parsed arguments
    fake_toolset.run.assert_called_once_with("get_quote", {"ticker": "AAPL"})

    call_evt = next(e for e in events if isinstance(e, ToolCallEvent))
    assert call_evt.name == "get_quote"
    assert call_evt.input == {"ticker": "AAPL"}
    assert call_evt.tool_use_id == "call_1"

    res_evt = next(e for e in events if isinstance(e, ToolResultEvent))
    assert res_evt.ok is True

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "AAPL is at 200."

    # second request carried the tool result back
    assert len(captured_calls) == 2
    second_msgs = captured_calls[1]["messages"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1" for m in second_msgs)

    # usage summed across both rounds (input 50+70, output 5+8)
    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.usage.input_tokens == 120
    assert usage.usage.output_tokens == 13


@pytest.mark.asyncio
async def test_openai_malformed_tool_args_degrades():
    """Invalid JSON arguments => error tool result, no toolset.run call, run still completes."""

    class _BadArgsStream:
        def __aiter__(self):
            async def gen():
                c = MagicMock()
                ch = MagicMock()
                ch.delta.content = None
                tc = MagicMock()
                tc.index = 0
                tc.id = "call_x"
                tc.function.name = "get_quote"
                tc.function.arguments = "{not json"
                ch.delta.tool_calls = [tc]
                ch.finish_reason = "tool_calls"
                c.choices = [ch]
                c.usage = MagicMock(
                    prompt_tokens=1, completion_tokens=1,
                    prompt_tokens_details=MagicMock(cached_tokens=0),
                )
                yield c

            return gen()

    streams = [_BadArgsStream(), _FakeTextStream()]
    fake = MagicMock()

    async def fake_create(**kwargs):
        return streams.pop(0)

    fake.chat.completions.create = fake_create
    fake_toolset = MagicMock()

    with (
        patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake),
        patch("apps.ai.providers.openai._resolve_toolset", return_value=fake_toolset),
    ):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5", system="x",
            messages=[ChatMessage(role="user", content="q")],
            tools=[{"type": "function", "function": {"name": "get_quote",
                    "description": "", "parameters": {}}}],
        )
        events = [evt async for evt in provider.run(req)]

    fake_toolset.run.assert_not_called()
    res_evt = next(e for e in events if isinstance(e, ToolResultEvent))
    assert res_evt.ok is False
    assert "json" in res_evt.error.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec web pytest backend/apps/ai/tests/test_openai_provider.py -v`
Expected: the two new tests FAIL (tools ignored → no `ToolCallEvent`; `_resolve_toolset` does not exist → `AttributeError` on patch). Existing `test_openai_streams_deltas_and_usage` and `test_openai_normalizes_system_prompt_as_message` still PASS.

- [ ] **Step 3: Write the implementation**

Replace the entire body of `backend/apps/ai/providers/openai.py` with the following (keeps `_cached` and `_openai_content` helpers, adds `json` import, `_resolve_toolset`, and the loop):

```python
"""OpenAI provider — streams via openai SDK, loops on tool_calls.

Also serves as the base for LocalProvider (see local.py) — the only difference
is base_url.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunRequest,
    TextDelta,
    TokenUsage,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        if base_url:
            self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = AsyncOpenAI(api_key=api_key)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import is_mock_mode

        if is_mock_mode():
            from apps.ai.providers._mock import mock_run

            async for ev in mock_run("openai"):
                yield ev
            return

        raw: list[dict] = [{"role": "system", "content": req.system}]
        for m in req.messages:
            raw.append({"role": m.role, "content": _openai_content(m.content)})

        total_in = total_out = total_cached = 0

        try:
            while True:
                create_kwargs: dict = dict(
                    model=req.model,
                    messages=cast(list[ChatCompletionMessageParam], raw),
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                if req.tools:
                    create_kwargs["tools"] = req.tools

                stream = await self._client.chat.completions.create(**create_kwargs)

                iter_text = ""
                tool_acc: dict[int, dict] = {}
                finish_reason: str | None = None

                async for chunk in stream:
                    for choice in getattr(chunk, "choices", None) or []:
                        delta = getattr(choice, "delta", None)
                        if delta is not None:
                            text = getattr(delta, "content", None)
                            if text:
                                iter_text += text
                                yield TextDelta(text=text)
                            for tc in getattr(delta, "tool_calls", None) or []:
                                slot = tool_acc.setdefault(
                                    tc.index, {"id": "", "name": "", "args": ""}
                                )
                                if getattr(tc, "id", None):
                                    slot["id"] = tc.id
                                fn = getattr(tc, "function", None)
                                if fn is not None:
                                    if getattr(fn, "name", None):
                                        slot["name"] = fn.name
                                    if getattr(fn, "arguments", None):
                                        slot["args"] += fn.arguments
                        if getattr(choice, "finish_reason", None):
                            finish_reason = choice.finish_reason
                    u = getattr(chunk, "usage", None)
                    if u is not None:
                        total_in += getattr(u, "prompt_tokens", 0) or 0
                        total_out += getattr(u, "completion_tokens", 0) or 0
                        total_cached += _cached(u)

                if finish_reason != "tool_calls" or not tool_acc:
                    break

                # Reconstruct the assistant tool_calls turn for the next request.
                ordered = [tool_acc[i] for i in sorted(tool_acc)]
                raw.append(
                    {
                        "role": "assistant",
                        "content": iter_text or None,
                        "tool_calls": [
                            {
                                "id": s["id"],
                                "type": "function",
                                "function": {"name": s["name"], "arguments": s["args"]},
                            }
                            for s in ordered
                        ],
                    }
                )

                toolset = _resolve_toolset()
                for s in ordered:
                    try:
                        parsed = json.loads(s["args"] or "{}")
                    except json.JSONDecodeError as exc:
                        parsed = {}
                        outcome = {"ok": False, "error": f"Invalid tool arguments JSON: {exc}"}
                    else:
                        yield ToolCallEvent(tool_use_id=s["id"], name=s["name"], input=parsed)
                        t0 = time.perf_counter()
                        outcome = toolset.run(s["name"], parsed)
                        latency_ms = int((time.perf_counter() - t0) * 1000)
                        yield ToolResultEvent(
                            tool_use_id=s["id"],
                            ok=bool(outcome.get("ok")),
                            result=outcome.get("result"),
                            error=str(outcome.get("error", "")),
                            latency_ms=latency_ms,
                        )
                        raw.append(
                            {
                                "role": "tool",
                                "tool_call_id": s["id"],
                                "content": str(
                                    outcome.get("result")
                                    if outcome.get("ok")
                                    else outcome.get("error")
                                ),
                            }
                        )
                        continue
                    # malformed-args branch: emit call (empty input) + error result
                    yield ToolCallEvent(tool_use_id=s["id"], name=s["name"], input=parsed)
                    yield ToolResultEvent(
                        tool_use_id=s["id"], ok=False, error=str(outcome.get("error", ""))
                    )
                    raw.append(
                        {
                            "role": "tool",
                            "tool_call_id": s["id"],
                            "content": str(outcome.get("error")),
                        }
                    )

            yield UsageEvent(
                usage=TokenUsage(
                    input_tokens=total_in,
                    output_tokens=total_out,
                    cached_tokens=total_cached,
                )
            )
            yield DoneEvent()
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _resolve_toolset():
    """Late import so tests can patch without importing market services."""
    from apps.ai.tools.registry import default_toolset

    return default_toolset()


def _cached(usage) -> int:
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    return getattr(details, "cached_tokens", 0) or 0


def _openai_content(content: str | list[dict]) -> str | list[dict]:
    """Normalize provider-shaped content to OpenAI's chat completion format.

    Text-only turns pass through as strings. Block lists already in OpenAI's
    `text`/`image_url` shape pass through. For each block lacking a `type`
    key, default to "text" with the raw string value.
    """
    if isinstance(content, str):
        return content
    out: list[dict] = []
    for block in content:
        if "type" in block:
            out.append(block)
            continue
        out.append({"type": "text", "text": str(block)})
    return out
```

Note: the malformed-args branch is slightly duplicated to keep the happy path readable. The `continue` after the happy-path result skips the malformed re-emit.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest backend/apps/ai/tests/test_openai_provider.py backend/apps/ai/tests/test_local_provider.py -v`
Expected: all PASS (new tool-loop tests + existing streaming/system-prompt tests + local provider tests, since LocalProvider inherits the new loop).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/ai/providers/openai.py backend/apps/ai/tests/test_openai_provider.py
git commit -m "feat(ai): tool-call loop for OpenAI/local providers"
```

---

## Task 3: `ProviderConfig.supports_tools` field + migration + serializer

**Files:**
- Modify: `backend/apps/secrets/models.py:59` (after `supports_vision`)
- Create: `backend/apps/secrets/migrations/0004_providerconfig_supports_tools.py`
- Modify: `backend/apps/secrets/serializers.py:19` (after `"supports_vision"`)
- Test: `backend/apps/secrets/tests/` (add to an existing serializer/model test file, or create `test_supports_tools.py`)

- [ ] **Step 1: Write the failing test**

Create `backend/apps/secrets/tests/test_supports_tools.py`:

```python
import pytest

from apps.secrets.models import ProviderConfig
from apps.secrets.serializers import ProviderConfigSerializer


@pytest.mark.django_db
def test_supports_tools_defaults_true():
    cfg = ProviderConfig.objects.create(provider="openai")
    assert cfg.supports_tools is True


@pytest.mark.django_db
def test_supports_tools_in_serializer():
    cfg = ProviderConfig.objects.create(provider="local", base_url="http://x/v1",
                                        supports_tools=False)
    data = ProviderConfigSerializer(cfg).data
    assert data["supports_tools"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/secrets/tests/test_supports_tools.py -v`
Expected: FAIL — `TypeError`/`FieldError` ("unexpected keyword 'supports_tools'") or `KeyError: 'supports_tools'`.

- [ ] **Step 3a: Add the model field**

In `backend/apps/secrets/models.py`, immediately after line 59 (`supports_vision = models.BooleanField(default=True)`):

```python
    supports_tools = models.BooleanField(default=True)
```

- [ ] **Step 3b: Generate the migration**

Run: `docker compose exec web python backend/manage.py makemigrations secrets`
Expected: creates `backend/apps/secrets/migrations/0004_providerconfig_supports_tools.py` adding a `BooleanField(default=True)`. (If the generator picks a different filename suffix, that's fine — keep whatever it generates.)

- [ ] **Step 3c: Expose in the serializer**

In `backend/apps/secrets/serializers.py`, add `"supports_tools",` to the `fields` list immediately after `"supports_vision",` (line 19).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/secrets/tests/test_supports_tools.py -v`
Expected: PASS (pytest-django applies the new migration to the test DB automatically).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/secrets/models.py backend/apps/secrets/migrations/ backend/apps/secrets/serializers.py backend/apps/secrets/tests/test_supports_tools.py
git commit -m "feat(secrets): add ProviderConfig.supports_tools flag"
```

---

## Task 4: `unsupported_features()` pure helper

**Files:**
- Create: `backend/apps/ai/capabilities.py`
- Test: `backend/apps/ai/tests/test_capabilities.py`

The helper takes the provider name, the thread's profile (or `None`), and the resolved `supports_tools` bool, and returns human-readable names of enabled-but-unhonorable features. It reads profile flags defensively with `getattr(..., False)` (the same way `_build_request` does today) so it works regardless of which profile model variant is present.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/ai/tests/test_capabilities.py`:

```python
from types import SimpleNamespace

import pytest

from apps.ai.capabilities import unsupported_features


def _profile(**flags):
    base = {"enable_tools": False, "enable_thinking": False, "enable_memory": False}
    base.update(flags)
    return SimpleNamespace(**base)


def test_claude_supports_everything():
    prof = _profile(enable_tools=True, enable_thinking=True, enable_memory=True)
    assert unsupported_features("claude", prof, supports_tools=False) == []


def test_none_profile_is_empty():
    assert unsupported_features("openai", None, supports_tools=True) == []


def test_openai_thinking_and_memory_unsupported():
    prof = _profile(enable_thinking=True, enable_memory=True)
    out = unsupported_features("openai", prof, supports_tools=True)
    assert "extended thinking" in out
    assert "memory" in out
    assert "tool use" not in out  # tools allowed when supports_tools=True


def test_local_tools_unsupported_when_flag_off():
    prof = _profile(enable_tools=True)
    assert unsupported_features("local", prof, supports_tools=False) == ["tool use"]


def test_local_tools_ok_when_flag_on():
    prof = _profile(enable_tools=True)
    assert unsupported_features("local", prof, supports_tools=True) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/ai/tests/test_capabilities.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.ai.capabilities'`

- [ ] **Step 3: Write the implementation**

Create `backend/apps/ai/capabilities.py`:

```python
"""Capability gap detection — which enabled profile features a provider can't honor.

Claude is the only M10-aware provider. OpenAI/local support tool use only when
the ProviderConfig opts in (supports_tools); extended thinking and memory remain
Claude-only. This helper drives a warn-and-continue message so the gap is visible
rather than a silent no-op.
"""

from __future__ import annotations


def unsupported_features(provider_name: str, profile, *, supports_tools: bool) -> list[str]:
    """Return human-readable names of features enabled on `profile` that
    `provider_name` cannot honor. Empty list => fully compatible."""
    if provider_name == "claude" or profile is None:
        return []
    out: list[str] = []
    if getattr(profile, "enable_tools", False) and not supports_tools:
        out.append("tool use")
    if getattr(profile, "enable_thinking", False):
        out.append("extended thinking")
    if getattr(profile, "enable_memory", False):
        out.append("memory")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/ai/tests/test_capabilities.py -v`
Expected: PASS (all 5)

- [ ] **Step 5: Commit**

```bash
git add backend/apps/ai/capabilities.py backend/apps/ai/tests/test_capabilities.py
git commit -m "feat(ai): unsupported_features capability helper"
```

---

## Task 5: Extend `_build_request` tool gating

**Files:**
- Modify: `backend/apps/threads/tasks.py:107-158` (`_build_request` signature + gating block) and its caller at line 366
- Test: `backend/apps/threads/tests/test_run_ai_routing.py`

`_build_request` currently builds tools only for Claude. Add a `supports_tools` parameter (default `False` — conservative guard), and build OpenAI-shaped tools for non-Claude providers when `enable_tools AND supports_tools`. The caller `run_ai_on_message` passes `supports_tools=cfg.supports_tools`.

- [ ] **Step 1: Write the failing test**

Add to `backend/apps/threads/tests/test_run_ai_routing.py`. Use **real ORM objects** — `_build_request` runs `Message.objects.filter(thread=thread, ...)`, so a fake non-model thread would raise. Mirror the fixture style in `test_snapshot_injection.py`:

```python
from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread
from apps.threads.tasks import _build_request


@pytest.fixture
def tools_thread(db):
    profile = TradingProfile.objects.create(
        name="Tooler", style="be helpful", enable_tools=True
    )
    thread = Thread.objects.create(kind="consult", profile=profile)
    msg = Message.objects.create(
        thread=thread, role="user", content={"text": "quote AAPL"}, status="done"
    )
    return thread, msg


@pytest.mark.django_db
def test_build_request_openai_tools_when_supported(tools_thread):
    thread, msg = tools_thread
    fake_tools = [{"type": "function", "function": {"name": "get_quote"}}]
    with patch("apps.ai.tools.registry.default_toolset") as ts:
        ts.return_value.openai_tools.return_value = fake_tools
        req = _build_request(thread, msg, provider_name="openai", supports_tools=True)
    assert req.tools == fake_tools


@pytest.mark.django_db
def test_build_request_openai_no_tools_when_unsupported(tools_thread):
    thread, msg = tools_thread
    req = _build_request(thread, msg, provider_name="local", supports_tools=False)
    assert req.tools == []


@pytest.mark.django_db
def test_build_request_claude_uses_anthropic_tools(tools_thread):
    thread, msg = tools_thread
    fake_tools = [{"name": "get_quote", "description": "", "input_schema": {}}]
    with patch("apps.ai.tools.registry.default_toolset") as ts:
        ts.return_value.anthropic_tools.return_value = fake_tools
        req = _build_request(thread, msg, provider_name="claude", supports_tools=False)
    assert req.tools == fake_tools
```

Note: confirm `Thread.objects.create(kind="consult", profile=profile)` matches the `Thread` model's required fields (check `apps/threads/models.py:Thread`); adjust `kind`/required args if needed. The `default_toolset` patch target is `apps.ai.tools.registry.default_toolset` because `_build_request` imports it lazily from that module.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec web pytest backend/apps/threads/tests/test_run_ai_routing.py -k build_request -v`
Expected: FAIL — `_build_request() got an unexpected keyword argument 'supports_tools'`.

- [ ] **Step 3: Edit `_build_request`**

In `backend/apps/threads/tasks.py`, change the signature (lines 107-112) to add the parameter:

```python
def _build_request(
    thread: Thread,
    user_msg: Message,
    *,
    provider_name: str = "claude",
    supports_tools: bool = False,
) -> RunRequest:
```

Then replace the gating block (lines 133-147, the `# M10:` comment through the `memory_dir = ...` line) with:

```python
    # M10: opt-in tool use / thinking / memory.
    # Tools: Claude always (anthropic shape); OpenAI/local when the endpoint opts in
    # (openai shape). Thinking + memory remain Claude-only.
    tools: list[dict] = []
    thinking_budget = 0
    memory_dir = ""
    if thread.profile:
        enable_tools = getattr(thread.profile, "enable_tools", False)
        if enable_tools and provider_name == "claude":
            from apps.ai.tools.registry import default_toolset

            tools = default_toolset().anthropic_tools()
        elif enable_tools and supports_tools:
            from apps.ai.tools.registry import default_toolset

            tools = default_toolset().openai_tools()
        if provider_name == "claude":
            if getattr(thread.profile, "enable_thinking", False):
                thinking_budget = int(getattr(thread.profile, "thinking_budget", 0) or 0)
            if getattr(thread.profile, "enable_memory", False):
                from apps.ai.memory import memory_dir_for_profile

                memory_dir = memory_dir_for_profile(profile_id=thread.profile.id)
```

- [ ] **Step 4a: Update the caller**

In `backend/apps/threads/tasks.py`, change line 366 from:

```python
    req = _build_request(thread, user_msg, provider_name=provider_name)
```

to:

```python
    req = _build_request(
        thread, user_msg, provider_name=provider_name, supports_tools=cfg.supports_tools
    )
```

- [ ] **Step 4b: Update observer + trigger callers (uniform parity)**

Find the other `_build_request` callers and pass `supports_tools` from their resolved `ProviderConfig`:

Run: `grep -rn "_build_request" backend/apps/observer backend/apps/triggers`

For each call site, pass `supports_tools=<cfg>.supports_tools` where `<cfg>` is that path's already-fetched `ProviderConfig`. If a path does not fetch a `ProviderConfig`, leave the call unchanged — the `supports_tools=False` default preserves today's behavior (no tools for non-Claude there). Document which you changed in the commit message.

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec web pytest backend/apps/threads/tests/test_run_ai_routing.py backend/apps/threads/tests/test_run_ai.py backend/apps/threads/tests/test_tool_calls.py -v`
Expected: all PASS (new gating tests + existing routing/run/tool-call tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/threads/tasks.py backend/apps/threads/tests/test_run_ai_routing.py backend/apps/observer backend/apps/triggers
git commit -m "feat(threads): build OpenAI/local tools in _build_request when supports_tools"
```

---

## Task 6: Capability warning emission + dedupe

**Files:**
- Modify: `backend/apps/threads/tasks.py` (`run_ai_on_message`, after the cost-cap block ~line 364, before `_build_request` at line 366); add a `_emit_capability_warning` helper near `_fail`
- Test: `backend/apps/threads/tests/test_run_ai.py`

When the resolved provider can't honor enabled profile features, write a `system`/`done` `Message` describing the gap and broadcast a WS `warning` event — then continue. Dedupe: skip if the thread's most recent `system` message already carries the identical warning text.

- [ ] **Step 1: Write the failing test**

Add to `backend/apps/threads/tests/test_run_ai.py` (inspect the file's existing fixtures/imports first; these tests create a `Thread`, a `ProviderConfig`, a profile with `enable_thinking=True`, and a user `Message`, then call `run_ai_on_message`. Reuse the file's existing factory helpers where present rather than re-creating them):

```python
from unittest.mock import patch

import pytest

from apps.threads.models import Message
from apps.threads.tasks import _emit_capability_warning


@pytest.mark.django_db
def test_emit_capability_warning_writes_system_message(thread_factory):
    # thread_factory: use whatever helper test_run_ai.py already defines to
    # create a Thread; if none exists, create Thread/Profile inline.
    thread = thread_factory()
    with patch("apps.threads.tasks._broadcast") as bc:
        wrote = _emit_capability_warning(
            thread_id=thread.id, features=["extended thinking"], provider_name="openai"
        )
    assert wrote is True
    msg = Message.objects.filter(thread=thread, role="system").latest("created_at")
    assert "extended thinking" in msg.content["text"]
    assert "openai" in msg.content["text"]
    assert bc.call_args[0][1]["event"] == "warning"


@pytest.mark.django_db
def test_emit_capability_warning_dedupes(thread_factory):
    thread = thread_factory()
    with patch("apps.threads.tasks._broadcast"):
        first = _emit_capability_warning(
            thread_id=thread.id, features=["memory"], provider_name="local"
        )
        second = _emit_capability_warning(
            thread_id=thread.id, features=["memory"], provider_name="local"
        )
    assert first is True
    assert second is False
    assert Message.objects.filter(thread=thread, role="system").count() == 1
```

If `test_run_ai.py` has no `thread_factory`, define a small module-level fixture in that file:

```python
@pytest.fixture
def thread_factory(db):
    from apps.threads.models import Thread

    def _make():
        return Thread.objects.create()

    return _make
```

(Adjust `Thread.objects.create()` to whatever required fields the model has — check `apps/threads/models.py:Thread`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec web pytest backend/apps/threads/tests/test_run_ai.py -k capability_warning -v`
Expected: FAIL — `cannot import name '_emit_capability_warning'`.

- [ ] **Step 3: Add the helper + wire it in**

In `backend/apps/threads/tasks.py`, add near `_fail` (after line 178):

```python
def _emit_capability_warning(
    *, thread_id: int, features: list[str], provider_name: str
) -> bool:
    """Write a system/done message + broadcast a WS warning when the selected
    provider can't honor enabled profile features. Deduped against the thread's
    most recent system message. Returns True if a message was written."""
    feature_list = ", ".join(features)
    text = (
        f"Heads up: provider '{provider_name}' does not support "
        f"{feature_list}. Those settings were ignored for this run."
    )
    last_system = (
        Message.objects.filter(thread_id=thread_id, role="system")
        .order_by("-created_at")
        .first()
    )
    if last_system is not None and last_system.content.get("text") == text:
        return False
    msg = Message.objects.create(
        thread_id=thread_id,
        role="system",
        content={"text": text},
        status="done",
    )
    _broadcast(thread_id, {"event": "warning", "message_id": msg.id, "text": text})
    return True
```

Then in `run_ai_on_message`, insert between the cost-cap block and `_build_request` (after line 364's `return ...` block closes, before line 366):

```python
    from apps.ai.capabilities import unsupported_features

    gaps = unsupported_features(
        provider_name, thread.profile, supports_tools=cfg.supports_tools
    )
    if gaps:
        _emit_capability_warning(
            thread_id=thread_id, features=gaps, provider_name=provider_name
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest backend/apps/threads/tests/test_run_ai.py -v`
Expected: all PASS (new warning tests + existing run-ai tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/threads/tasks.py backend/apps/threads/tests/test_run_ai.py
git commit -m "feat(threads): visible warning when provider can't honor profile features"
```

---

## Task 7: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (update the "Only `apps/ai/providers/claude.py` is M10-aware" bullet)

- [ ] **Step 1: Run the full backend lint + test suite**

Run: `make lint && make test`
Expected: PASS. (If `make test` is heavy, at minimum run `docker compose exec web pytest backend/apps/ai backend/apps/threads backend/apps/secrets -v`.)

- [ ] **Step 2: Update CLAUDE.md**

Find the bullet beginning "Only `apps/ai/providers/claude.py` is M10-aware." and revise it to reflect that **tool use now works on OpenAI/local** (opt-in via `ProviderConfig.supports_tools`), while thinking/memory/files/citations remain Claude-only, and that enabling an unsupported feature on a non-Claude profile now emits a visible `system` warning message + `warning` WS event rather than being a silent no-op. Replace, don't append.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note OpenAI/local tool parity + capability warnings"
```

- [ ] **Step 4: Push + open PR**

```bash
git push -u origin feat/provider-tool-parity
gh pr create --title "feat: OpenAI/local tool-calling parity + capability warnings" \
  --body "Implements docs/superpowers/specs/2026-05-26-provider-tool-parity-design.md"
```

---

## Self-Review Notes

- **Spec coverage:** `openai_tools()` (T1), OpenAI tool loop incl. malformed-args degradation (T2), `supports_tools` field/migration/serializer (T3), `unsupported_features` (T4), `_build_request` gating matrix + uniform observer/trigger wiring (T5), warn-and-continue system message + WS event + dedupe (T6), CLAUDE.md update + full verification (T7). All spec sections mapped.
- **Type consistency:** `openai_tools()` shape `{type:"function", function:{name,description,parameters}}` is produced in T1 and consumed verbatim by the T2 loop (`create_kwargs["tools"] = req.tools`) and asserted in T5. `_emit_capability_warning` signature matches its call site and tests. `unsupported_features(provider_name, profile, *, supports_tools)` signature is identical in T4 definition and T6 call site.
- **Error handling:** endpoint-rejects-tools (existing `except Exception` → `ErrorEvent`), endpoint-ignores-tools (`finish_reason != "tool_calls"` → loop exits), malformed args (error tool result, no `toolset.run`), unknown tool (existing `Toolset.run`).
