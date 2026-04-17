# M4 Full Threads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Broaden AI coverage beyond one-shot consult. Add OpenAI + Local providers (OpenAI-compatible), promote threads to multi-turn chat mode, add multi-provider compare, polish cost tracking, and tighten the UI. After M4, you can have ongoing conversations with any provider, branch a single prompt across providers to compare, and watch today's spend live per-provider.

**Architecture:**
- `apps.ai.providers.openai` (new) — OpenAIProvider using the `openai` SDK against `api.openai.com`.
- `apps.ai.providers.local` (new) — LocalProvider using the same `openai` SDK but with a user-configured `base_url` (Ollama / LM Studio / vLLM / llama.cpp / LocalAI).
- `apps.ai.catalog.py` (modify) — add OpenAI + local entries; `cost_unknown=True` for local.
- `apps.ai.router.py` (new) — resolves `(provider, model)` per spec §6.5 precedence (message override → thread default → profile default → ProviderConfig first enabled).
- `apps.threads.tasks.py` (modify) — add `parent_message_id` / branch support; route via `apps.ai.router`; multi-provider compare path.
- `apps.threads.models.py` (modify) — `parent_message` FK already exists from M3; add `branch_tag` helper for UI labeling.
- Costs dashboard endpoint + page.
- Frontend: provider+model picker on the thread composer, compare UI, costs page, small polish on `StreamingMessage` (stop button + cost chip).

**Tech Stack (additions to M3):**
- `openai` Python SDK (used by OpenAIProvider + LocalProvider).
- Frontend: small polish — no new libraries.

---

## File Layout Added by This Plan

```
backend/apps/ai/
├── providers/
│   ├── openai.py                     # OpenAIProvider (hosted) — async streaming via openai SDK
│   ├── local.py                      # LocalProvider (OpenAI-compatible base_url)
│   └── __init__.py                   # (modify) re-export factory get_provider()
├── router.py                         # Resolve (provider, model) per spec precedence
├── catalog.py                        # (modify) add OpenAI + Local rows
└── tests/
    ├── test_openai_provider.py
    ├── test_local_provider.py
    ├── test_router.py
    └── test_catalog_openai.py

backend/apps/threads/
├── tasks.py                          # (modify) use router + branch support + compare
├── views.py                          # (modify) new /threads/<id>/compare + /threads/<id>/stop/<mid>
├── serializers.py                    # (modify) expose parent_message + branch siblings
├── services.py                       # (new) build_chat_messages helper for multi-turn
└── tests/
    ├── test_run_ai_routing.py
    ├── test_compare.py
    └── test_chat_history.py

backend/apps/secrets/
├── models.py                         # (modify) add supports_vision toggle use + local base_url validation
└── urls.py                           # (modify) — nothing new; keep /api/schwab/ prefix

backend/apps/costs/                   # New app — today/week/month aggregates
├── __init__.py  apps.py  urls.py
├── views.py                          # /api/costs/today, /api/costs/range
├── services.py                       # cost_breakdown_for(period)
└── tests/test_costs.py

frontend/src/
├── api/
│   ├── costs.ts                      # fetchCostsToday, fetchCostsRange
│   └── threads.ts                    # (modify) add compareMessage, stopMessage
├── hooks/
│   ├── useCosts.ts
│   └── useThread.ts                  # (modify) add compare mutation + stop mutation
├── components/
│   ├── ProviderModelPicker.tsx       # <select provider><select model> for composer + thread
│   ├── CompareDialog.tsx             # choose 2-3 providers/models for a single send
│   ├── BranchTabs.tsx                # tabs across parent_message siblings
│   ├── CostChip.tsx                  # $0.04 pill linking to /costs
│   ├── StopButton.tsx                # cancel a streaming message
│   └── StreamingMessage.tsx          # (modify) show cost chip + model badge
├── pages/
│   ├── ThreadDetailPage.tsx          # (modify) integrate picker + compare + branches + stop
│   ├── CostsPage.tsx                 # new /costs
│   └── Dashboard.tsx                 # (modify) add "today's spend" widget + link
└── router.tsx                        # (modify) add /costs
```

Responsibility recap:
- **Provider implementations** keep the M3 provider protocol; no changes to `apps.ai.types`.
- **Routing** is a pure function; it doesn't know about DB except via the input objects (Message, Thread, Profile).
- **Compare** is still a single DRF endpoint + single Celery dispatch — but creates N parallel assistant messages under the same user-message parent.

---

## Task 1: Install M4 dependencies

**Files:** `pyproject.toml`

- [ ] **Step 1.1: Add the OpenAI Python SDK**

In `pyproject.toml` `[project].dependencies`, after the `"anthropic>=..."` line:

```toml
    "openai>=1.54,<2.0",
```

- [ ] **Step 1.2: Rebuild + verify**

```bash
cd /home/dan/ai-dashboard
docker compose build web worker beat
docker compose up -d
sleep 8
docker compose exec web python -c "import openai; print('ok', openai.__version__)"
```

Expected: `ok` + a 1.x version string.

- [ ] **Step 1.3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add openai SDK for M4"
```

---

## Task 2: Catalog — add OpenAI + Local entries (TDD)

**Files:**
- Modify: `backend/apps/ai/catalog.py`
- Create: `backend/apps/ai/tests/test_catalog_openai.py`

- [ ] **Step 2.1: Write failing test**

Write `backend/apps/ai/tests/test_catalog_openai.py`:

```python
from apps.ai.catalog import list_models, get_model


def test_openai_models_in_catalog():
    ids = [m.id for m in list_models("openai")]
    assert "gpt-5" in ids
    assert "gpt-5-mini" in ids


def test_openai_pricing_reasonable():
    m = get_model("openai", "gpt-5")
    assert m is not None
    assert m.input_per_mtok > 0
    assert m.output_per_mtok > m.input_per_mtok


def test_local_models_absent_by_default():
    """Local provider catalog is empty — users declare their own model names at runtime."""
    local = list_models("local")
    assert local == []
```

- [ ] **Step 2.2: Extend `backend/apps/ai/catalog.py`**

In `_CATALOG`, after the Claude entries, add:

```python
    # OpenAI
    ModelInfo(
        provider="openai", id="gpt-5", name="GPT-5",
        input_per_mtok=5.00, output_per_mtok=40.00, cached_per_mtok=0.50,
        context_window=400_000, supports_vision=True, supports_cache=True,
    ),
    ModelInfo(
        provider="openai", id="gpt-5-mini", name="GPT-5 Mini",
        input_per_mtok=0.60, output_per_mtok=4.80, cached_per_mtok=0.06,
        context_window=400_000, supports_vision=True, supports_cache=True,
    ),
    ModelInfo(
        provider="openai", id="gpt-5-nano", name="GPT-5 Nano",
        input_per_mtok=0.15, output_per_mtok=1.20, cached_per_mtok=0.015,
        context_window=400_000, supports_vision=False, supports_cache=True,
    ),
```

(Pricing is a best-effort estimate as of 2026-04. Catalog is a committed source of truth; update when the user learns real prices.)

Local models are NOT added — Local provider is declared by the user at runtime via `ProviderConfig.default_model` + any free-form id.

- [ ] **Step 2.3: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_catalog_openai.py apps/ai/tests/test_catalog.py -v
git add backend/apps/ai/catalog.py backend/apps/ai/tests/test_catalog_openai.py
git commit -m "feat(ai): add OpenAI catalog entries (gpt-5, gpt-5-mini, gpt-5-nano)"
```

Expected: M3 catalog tests still pass + 3 new ones pass.

---

## Task 3: OpenAIProvider (TDD)

**Files:**
- Create: `backend/apps/ai/providers/openai.py`
- Create: `backend/apps/ai/tests/test_openai_provider.py`

- [ ] **Step 3.1: Write failing test**

Write `backend/apps/ai/tests/test_openai_provider.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from apps.ai.providers.openai import OpenAIProvider
from apps.ai.types import ChatMessage, DoneEvent, RunRequest, TextDelta, UsageEvent


class _FakeOpenAIStream:
    """Mimics openai.AsyncStream yielding ChatCompletionChunks."""

    def __init__(self, text_chunks, usage):
        self._text_chunks = text_chunks
        self._usage = usage

    def __aiter__(self):
        async def gen():
            for c in self._text_chunks:
                chunk = MagicMock()
                choice = MagicMock()
                choice.delta.content = c
                chunk.choices = [choice]
                chunk.usage = None
                yield chunk
            # Final chunk with usage (OpenAI streams usage last when stream_options.include_usage=True)
            final = MagicMock()
            final.choices = []
            final.usage = MagicMock(
                prompt_tokens=self._usage["input"],
                completion_tokens=self._usage["output"],
                prompt_tokens_details=MagicMock(cached_tokens=self._usage.get("cached", 0)),
            )
            yield final
        return gen()


@pytest.mark.asyncio
async def test_openai_streams_deltas_and_usage():
    fake = MagicMock()

    async def fake_create(**kwargs):
        return _FakeOpenAIStream(
            ["Hello", " ", "world"], {"input": 80, "output": 20, "cached": 10},
        )

    fake.chat.completions.create = fake_create
    with patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5", system="You help.",
            messages=[ChatMessage(role="user", content="hi")],
        )
        events = []
        async for evt in provider.run(req):
            events.append(evt)

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "Hello world"

    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.usage.input_tokens == 80
    assert usage.usage.output_tokens == 20
    assert usage.usage.cached_tokens == 10

    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_openai_normalizes_system_prompt_as_message():
    """OpenAI expects system as a message, not a top-level block like Claude."""
    captured = {}

    fake = MagicMock()

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeOpenAIStream(["ok"], {"input": 1, "output": 1})

    fake.chat.completions.create = fake_create
    with patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5", system="YOU_ARE_A_TRADER",
            messages=[ChatMessage(role="user", content="hi")],
        )
        async for _ in provider.run(req):
            pass

    sent = captured["messages"]
    assert sent[0] == {"role": "system", "content": "YOU_ARE_A_TRADER"}
    assert sent[1] == {"role": "user", "content": "hi"}
```

- [ ] **Step 3.2: Write `backend/apps/ai/providers/openai.py`**

```python
"""OpenAI provider — streams via openai SDK.

Also serves as the base for LocalProvider (see local.py) — the only difference
is base_url.
"""
from __future__ import annotations

from typing import AsyncIterator

from openai import AsyncOpenAI

from apps.ai.types import (
    DoneEvent, ErrorEvent, RunEvent, RunRequest, TextDelta, TokenUsage, UsageEvent,
)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        messages: list[dict] = [{"role": "system", "content": req.system}]
        for m in req.messages:
            messages.append({"role": m.role, "content": m.content})

        try:
            stream = await self._client.chat.completions.create(
                model=req.model,
                messages=messages,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                stream=True,
                stream_options={"include_usage": True},
            )
            usage_data = TokenUsage()
            async for chunk in stream:
                if getattr(chunk, "choices", None):
                    for choice in chunk.choices:
                        delta = getattr(choice, "delta", None)
                        text = getattr(delta, "content", None) if delta else None
                        if text:
                            yield TextDelta(text=text)
                u = getattr(chunk, "usage", None)
                if u is not None:
                    usage_data = TokenUsage(
                        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
                        output_tokens=getattr(u, "completion_tokens", 0) or 0,
                        cached_tokens=_cached(u),
                    )
            yield UsageEvent(usage=usage_data)
            yield DoneEvent()
        except Exception as exc:  # noqa: BLE001
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _cached(usage) -> int:
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    return getattr(details, "cached_tokens", 0) or 0
```

- [ ] **Step 3.3: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_openai_provider.py -v
git add backend/apps/ai/providers/openai.py backend/apps/ai/tests/test_openai_provider.py
git commit -m "feat(ai): OpenAIProvider with streaming + usage"
```

Expected: 2 passed.

---

## Task 4: LocalProvider (TDD)

**Files:**
- Create: `backend/apps/ai/providers/local.py`
- Create: `backend/apps/ai/tests/test_local_provider.py`

- [ ] **Step 4.1: Write failing test**

Write `backend/apps/ai/tests/test_local_provider.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from apps.ai.providers.local import LocalProvider


def test_local_requires_base_url():
    with pytest.raises(ValueError):
        LocalProvider(api_key="", base_url="")


def test_local_name_is_local():
    p = LocalProvider(api_key="", base_url="http://localhost:11434/v1")
    assert p.name == "local"


@pytest.mark.asyncio
async def test_local_reuses_openai_streaming_shape():
    """LocalProvider.run should behave identically to OpenAIProvider.run when
    given an OpenAI-compatible endpoint. We verify this by patching AsyncOpenAI
    and checking the call includes our base_url."""
    captured = {}

    class _FakeClient:
        def __init__(self, **kw):
            captured.update(kw)
            self.chat = MagicMock()

            async def create(**kwargs):
                async def gen():
                    chunk = MagicMock()
                    choice = MagicMock()
                    choice.delta.content = "hello"
                    chunk.choices = [choice]
                    chunk.usage = None
                    yield chunk
                    final = MagicMock()
                    final.choices = []
                    final.usage = MagicMock(
                        prompt_tokens=1, completion_tokens=1,
                        prompt_tokens_details=MagicMock(cached_tokens=0),
                    )
                    yield final
                return _AsyncIter(gen())

            self.chat.completions.create = create

    class _AsyncIter:
        def __init__(self, it):
            self._it = it
        def __aiter__(self):
            return self._it

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeClient):
        from apps.ai.types import ChatMessage, RunRequest
        p = LocalProvider(api_key="", base_url="http://host.docker.internal:11434/v1")
        req = RunRequest(model="llama3", system="x", messages=[ChatMessage(role="user", content="hi")])
        async for _ in p.run(req):
            pass

    assert captured["base_url"].startswith("http://host.docker.internal")
```

- [ ] **Step 4.2: Write `backend/apps/ai/providers/local.py`**

```python
"""Local provider — OpenAI-compatible endpoint (Ollama / LM Studio / vLLM / …).

Mechanically identical to OpenAIProvider; only name + base_url validation differ.
"""
from __future__ import annotations

from apps.ai.providers.openai import OpenAIProvider


class LocalProvider(OpenAIProvider):
    name = "local"

    def __init__(self, api_key: str, base_url: str) -> None:
        if not base_url:
            raise ValueError("LocalProvider requires a base_url (e.g. http://host.docker.internal:11434/v1).")
        super().__init__(api_key=api_key or "sk-local-placeholder", base_url=base_url)
```

`AsyncOpenAI` requires a non-empty api_key; many local servers ignore it, so we default to a placeholder when the user doesn't provide one.

- [ ] **Step 4.3: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_local_provider.py -v
git add backend/apps/ai/providers/local.py backend/apps/ai/tests/test_local_provider.py
git commit -m "feat(ai): LocalProvider (OpenAI-compatible endpoint)"
```

Expected: 3 passed.

---

## Task 5: Provider factory (TDD)

**Files:**
- Modify: `backend/apps/ai/providers/__init__.py`
- Create: `backend/apps/ai/tests/test_provider_factory.py`

- [ ] **Step 5.1: Write failing test**

Write `backend/apps/ai/tests/test_provider_factory.py`:

```python
from unittest.mock import patch

import pytest

from apps.ai.providers import get_provider
from apps.ai.providers.claude import ClaudeProvider
from apps.ai.providers.local import LocalProvider
from apps.ai.providers.openai import OpenAIProvider


def test_get_provider_claude():
    with patch("apps.ai.providers.claude.AsyncAnthropic"):
        p = get_provider("claude", api_key="sk-ant-x")
    assert isinstance(p, ClaudeProvider)


def test_get_provider_openai():
    with patch("apps.ai.providers.openai.AsyncOpenAI"):
        p = get_provider("openai", api_key="sk-oai-x")
    assert isinstance(p, OpenAIProvider)
    # Must not be the Local subclass
    assert not isinstance(p, LocalProvider)


def test_get_provider_local():
    with patch("apps.ai.providers.openai.AsyncOpenAI"):
        p = get_provider("local", api_key="", base_url="http://localhost:11434/v1")
    assert isinstance(p, LocalProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("imaginary", api_key="x")
```

- [ ] **Step 5.2: Write `backend/apps/ai/providers/__init__.py`**

Replace the existing empty `__init__.py`:

```python
"""Provider factory — resolves provider name to an instance.

Callers never `from apps.ai.providers.claude import ClaudeProvider` directly
in the task code; they go through `get_provider(...)`.
"""
from __future__ import annotations

from apps.ai.providers.base import Provider
from apps.ai.providers.claude import ClaudeProvider
from apps.ai.providers.local import LocalProvider
from apps.ai.providers.openai import OpenAIProvider


def get_provider(name: str, *, api_key: str, base_url: str = "") -> Provider:
    if name == "claude":
        return ClaudeProvider(api_key=api_key, base_url=base_url)
    if name == "openai":
        return OpenAIProvider(api_key=api_key, base_url=base_url)
    if name == "local":
        return LocalProvider(api_key=api_key, base_url=base_url)
    raise ValueError(f"Unknown provider: {name}")


__all__ = ["Provider", "ClaudeProvider", "OpenAIProvider", "LocalProvider", "get_provider"]
```

- [ ] **Step 5.3: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_provider_factory.py -v
git add backend/apps/ai/providers/__init__.py backend/apps/ai/tests/test_provider_factory.py
git commit -m "feat(ai): provider factory get_provider()"
```

Expected: 4 passed.

---

## Task 6: Router — (provider, model) resolution (TDD)

**Files:**
- Create: `backend/apps/ai/router.py`
- Create: `backend/apps/ai/tests/test_router.py`

- [ ] **Step 6.1: Write failing test**

Write `backend/apps/ai/tests/test_router.py`:

```python
import pytest

from apps.ai.router import resolve_provider_and_model, ResolutionError
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread


@pytest.mark.django_db
def test_resolves_from_profile_default():
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    ProviderConfig.objects.create(provider="openai", default_model="gpt-5")

    resolved = resolve_provider_and_model(thread=t, message=None, override=None)
    assert resolved == ("openai", "gpt-5-mini")


@pytest.mark.django_db
def test_override_wins_over_profile():
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    ProviderConfig.objects.create(provider="claude")
    ProviderConfig.objects.create(provider="openai")

    resolved = resolve_provider_and_model(
        thread=t, message=None,
        override={"provider": "claude", "model": "claude-opus-4-7"},
    )
    assert resolved == ("claude", "claude-opus-4-7")


@pytest.mark.django_db
def test_falls_back_to_providerconfig_when_no_profile():
    t = Thread.objects.create(kind="chat", profile=None, title="x")
    ProviderConfig.objects.create(provider="claude", default_model="claude-haiku-4-5-20251001")

    resolved = resolve_provider_and_model(thread=t, message=None, override=None)
    assert resolved == ("claude", "claude-haiku-4-5-20251001")


@pytest.mark.django_db
def test_no_providers_configured_raises():
    t = Thread.objects.create(kind="chat", profile=None, title="x")

    with pytest.raises(ResolutionError):
        resolve_provider_and_model(thread=t, message=None, override=None)
```

- [ ] **Step 6.2: Write `backend/apps/ai/router.py`**

```python
"""Resolve (provider, model) for an AI run per spec §6.5 precedence:

1. Per-send override
2. Thread.default_provider / .default_model (M5 — threads don't have these yet)
3. Profile.default_provider / .default_model
4. First enabled ProviderConfig (+ its default_model)
"""
from __future__ import annotations

from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread


class ResolutionError(RuntimeError):
    """No provider could be resolved — surface to the UI as a 400-level error."""


def resolve_provider_and_model(
    *,
    thread: Thread,
    message: Message | None = None,
    override: dict | None = None,
) -> tuple[str, str]:
    """Return (provider_name, model_id). Raises ResolutionError if nothing matches."""
    if override:
        p = override.get("provider")
        m = override.get("model")
        if p and m:
            return p, m

    if thread.profile:
        p = thread.profile.default_provider or None
        m = thread.profile.default_model or None
        if p and m:
            return p, m
        if p:
            cfg = ProviderConfig.objects.filter(provider=p, enabled=True).first()
            if cfg and cfg.default_model:
                return p, cfg.default_model

    cfg = ProviderConfig.objects.filter(enabled=True).order_by("id").first()
    if cfg and cfg.default_model:
        return cfg.provider, cfg.default_model

    raise ResolutionError("No provider configured. Visit /settings to add one.")
```

- [ ] **Step 6.3: Test + commit**

```bash
docker compose exec web pytest apps/ai/tests/test_router.py -v
git add backend/apps/ai/router.py backend/apps/ai/tests/test_router.py
git commit -m "feat(ai): provider+model router with precedence rules"
```

Expected: 4 passed.

---

## Task 7: AI run task — route through factory + router (TDD)

**Files:**
- Modify: `backend/apps/threads/tasks.py`
- Create: `backend/apps/threads/tests/test_run_ai_routing.py`

- [ ] **Step 7.1: Write failing test**

Write `backend/apps/threads/tests/test_run_ai_routing.py`:

```python
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_uses_openai_when_profile_defaults_to_openai():
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    calls = {}

    async def fake_run(self, req):
        calls["provider_name"] = self.name
        calls["model"] = req.model
        yield TextDelta(text="out")
        yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5))
        yield DoneEvent()

    with patch("apps.ai.providers.openai.OpenAIProvider.run", fake_run):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is True
    assert calls["provider_name"] == "openai"
    assert calls["model"] == "gpt-5-mini"


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_override_routes_to_claude():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-x")
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta

    calls = {}

    async def fake_run(self, req):
        calls["provider_name"] = self.name
        calls["model"] = req.model
        yield TextDelta(text="hi")
        yield DoneEvent()

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_run):
        result = run_ai_on_message.delay(
            thread_id=t.id, user_message_id=u.id,
            override={"provider": "claude", "model": "claude-opus-4-7"},
        ).get(timeout=5)

    assert result["ok"] is True
    assert calls["provider_name"] == "claude"
    assert calls["model"] == "claude-opus-4-7"
```

- [ ] **Step 7.2: Update `backend/apps/threads/tasks.py`**

Replace the old `run_ai_on_message` implementation (which hard-coded `ClaudeProvider`) with a routed version. Full file contents:

```python
"""AI run Celery task — drives a provider chosen by the router."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.db import transaction

from apps.ai.cost import CostCapExceededError, check_daily_cap, cost_usd_for
from apps.ai.providers import get_provider
from apps.ai.router import ResolutionError, resolve_provider_and_model
from apps.ai.types import (
    ChatMessage, DoneEvent, ErrorEvent, RunRequest, TextDelta, UsageEvent,
)
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread


def _broadcast(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        f"thread.{thread_id}", {"type": "thread_event", "payload": payload}
    )


async def _broadcast_async(thread_id: int, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(f"thread.{thread_id}", {"type": "thread_event", "payload": payload})


def _build_request(thread: Thread, user_msg: Message) -> RunRequest:
    system = thread.profile.style if thread.profile else ""
    history = list(
        Message.objects
        .filter(thread=thread, role__in=["user", "assistant"], status="done")
        .order_by("created_at")
    )
    chat_messages: list[ChatMessage] = [
        ChatMessage(role=m.role, content=_extract_text(m))
        for m in history
    ]
    if not any(m.id == user_msg.id for m in history):
        chat_messages.append(ChatMessage(role="user", content=_extract_text(user_msg)))
    return RunRequest(model="", system=system, messages=chat_messages, cache_system=True)


def _extract_text(m: Message) -> str:
    c = m.content or {}
    if isinstance(c, dict) and "text" in c:
        return c["text"]
    return str(c)


@shared_task(name="threads.run_ai_on_message")
def run_ai_on_message(
    *,
    thread_id: int,
    user_message_id: int,
    override: dict | None = None,
    parent_message_id: int | None = None,
) -> dict:
    thread = Thread.objects.select_related("profile").get(id=thread_id)
    user_msg = Message.objects.get(id=user_message_id)

    try:
        provider_name, model_id = resolve_provider_and_model(
            thread=thread, message=user_msg, override=override,
        )
    except ResolutionError as exc:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=str(exc), parent_message_id=parent_message_id,
        )
        _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": str(exc)})
        return {"ok": False, "error": "no_provider"}

    try:
        cfg = ProviderConfig.objects.get(provider=provider_name)
    except ProviderConfig.DoesNotExist:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=f"No ProviderConfig row for '{provider_name}'. Visit /settings.",
            parent_message_id=parent_message_id,
        )
        _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": assistant.error})
        return {"ok": False, "error": "no_key"}

    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
    except CostCapExceededError as exc:
        assistant = Message.objects.create(
            thread=thread, role="assistant", content={"text": ""}, status="failed",
            error=str(exc), parent_message_id=parent_message_id,
        )
        _broadcast(thread_id, {"event": "cost_capped", "message_id": assistant.id, "error": str(exc)})
        return {"ok": False, "error": "cost_capped"}

    req = _build_request(thread, user_msg)
    req.model = model_id

    assistant = Message.objects.create(
        thread=thread, role="assistant", content={"text": ""}, status="streaming",
        parent_message_id=parent_message_id,
    )
    _broadcast(thread_id, {
        "event": "message_started", "message_id": assistant.id,
        "parent_message_id": parent_message_id,
        "provider": provider_name, "model": model_id,
    })

    provider = get_provider(provider_name, api_key=cfg.api_key, base_url=cfg.base_url or "")
    t0 = time.perf_counter()
    buffer: list[str] = []
    usage = None
    err: str | None = None

    async def drive():
        nonlocal usage, err
        async for evt in provider.run(req):
            if isinstance(evt, TextDelta):
                buffer.append(evt.text)
                await _broadcast_async(thread_id, {
                    "event": "text_delta", "message_id": assistant.id, "text": evt.text,
                })
            elif isinstance(evt, UsageEvent):
                usage = evt.usage
            elif isinstance(evt, ErrorEvent):
                err = evt.message
            elif isinstance(evt, DoneEvent):
                return

    asyncio.run(drive())
    latency_ms = int((time.perf_counter() - t0) * 1000)

    with transaction.atomic():
        if err:
            assistant.content = {"text": "".join(buffer)}
            assistant.status = "failed"
            assistant.error = err
            assistant.save()
            AIRun.objects.create(
                message=assistant, provider=provider_name, model=model_id,
                status="failed", error=err, latency_ms=latency_ms,
            )
            _broadcast(thread_id, {"event": "error", "message_id": assistant.id, "error": err})
            return {"ok": False, "error": err}

        assistant.content = {"text": "".join(buffer)}
        assistant.status = "done"
        assistant.save()

        cost = Decimal("0") if usage is None else cost_usd_for(provider_name, model_id, usage)
        AIRun.objects.create(
            message=assistant, provider=provider_name, model=model_id,
            input_tokens=(usage.input_tokens if usage else 0),
            output_tokens=(usage.output_tokens if usage else 0),
            cached_tokens=(usage.cached_tokens if usage else 0),
            cost_usd=cost, latency_ms=latency_ms, status="done",
        )
        _broadcast(thread_id, {
            "event": "message_done", "message_id": assistant.id, "cost_usd": str(cost),
        })
        return {"ok": True}
```

- [ ] **Step 7.3: Test + commit**

```bash
docker compose exec web pytest apps/threads/tests/test_run_ai_routing.py apps/threads/tests/test_run_ai.py -v
git add backend/apps/threads/tasks.py backend/apps/threads/tests/test_run_ai_routing.py
git commit -m "feat(threads): route AI runs through provider factory + router"
```

Expected: 2 new routing tests + 2 existing M3 tests all pass.

---

## Task 8: Multi-provider compare endpoint (TDD)

**Files:**
- Modify: `backend/apps/threads/views.py`
- Create: `backend/apps/threads/tests/test_compare.py`

- [ ] **Step 8.1: Write failing test**

Write `backend/apps/threads/tests/test_compare.py`:

```python
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_compare_enqueues_one_task_per_branch(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")

    with patch("apps.threads.views.run_ai_on_message.delay") as enqueue:
        resp = api.post(
            f"/api/threads/{t.id}/compare/",
            {
                "text": "what about NVDA?",
                "branches": [
                    {"provider": "claude", "model": "claude-sonnet-4-6"},
                    {"provider": "openai", "model": "gpt-5-mini"},
                ],
            },
            format="json",
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "user_message_id" in body
    assert len(body["branches"]) == 2
    assert enqueue.call_count == 2
    # Each branch call receives parent_message_id = the user message id
    for call in enqueue.call_args_list:
        assert call.kwargs["parent_message_id"] == body["user_message_id"]

    # Only one user Message was created
    assert Message.objects.filter(thread=t, role="user").count() == 1


@pytest.mark.django_db
def test_compare_rejects_empty_branches(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    r = api.post(
        f"/api/threads/{t.id}/compare/", {"text": "hi", "branches": []}, format="json",
    )
    assert r.status_code == 400
```

- [ ] **Step 8.2: Extend `backend/apps/threads/views.py`**

Add a `compare` action to `ThreadViewSet`:

```python
    @action(detail=True, methods=["post"])
    def compare(self, request, pk=None):
        """Send ONE user message and fan out to N provider/model branches.

        Body: {text, branches: [{provider, model}, ...]}
        """
        thread = self.get_object()
        text = (request.data.get("text") or "").strip()
        branches = request.data.get("branches") or []
        if not text:
            return Response({"code": "empty", "message": "text is required"}, status=400)
        if not branches:
            return Response({"code": "no_branches", "message": "Provide at least one branch"}, status=400)

        user_msg = Message.objects.create(
            thread=thread, role="user", content={"text": text}, status="done",
        )
        branch_ids: list[dict] = []
        for b in branches:
            task = run_ai_on_message.delay(
                thread_id=thread.id,
                user_message_id=user_msg.id,
                override={"provider": b["provider"], "model": b["model"]},
                parent_message_id=user_msg.id,
            )
            branch_ids.append({"provider": b["provider"], "model": b["model"], "task_id": task.id})

        return Response(
            {"user_message_id": user_msg.id, "branches": branch_ids},
            status=202,
        )
```

- [ ] **Step 8.3: Test + commit**

```bash
docker compose exec web pytest apps/threads/tests/test_compare.py -v
git add backend/apps/threads/views.py backend/apps/threads/tests/test_compare.py
git commit -m "feat(threads): /threads/<id>/compare endpoint for multi-provider fan-out"
```

Expected: 2 passed.

---

## Task 9: Expose parent_message in Message serializer + chat history filter (TDD)

**Files:**
- Modify: `backend/apps/threads/serializers.py`
- Create: `backend/apps/threads/tests/test_chat_history.py`

- [ ] **Step 9.1: Update `MessageSerializer`**

Edit `backend/apps/threads/serializers.py`:

```python
class MessageSerializer(serializers.ModelSerializer):
    ai_run = AIRunSerializer(read_only=True)
    parent_message_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Message
        fields = [
            "id", "role", "content", "status", "error", "created_at",
            "ai_run", "parent_message_id",
        ]
```

- [ ] **Step 9.2: Write failing test**

Write `backend/apps/threads/tests/test_chat_history.py`:

```python
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_chat_mode_passes_full_history_to_provider():
    """Multi-turn chat: the second send should include the first exchange."""
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-x")
    p = TradingProfile.objects.create(
        name="P", style="You trade.", default_provider="claude", default_model="claude-sonnet-4-6",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")

    # Seed a prior exchange.
    Message.objects.create(thread=t, role="user", content={"text": "first question"}, status="done")
    Message.objects.create(thread=t, role="assistant", content={"text": "first answer"}, status="done")

    from apps.threads.tasks import run_ai_on_message
    from apps.ai.types import DoneEvent, TextDelta

    captured = {}

    async def fake_run(self, req):
        captured["messages"] = [(m.role, m.content) for m in req.messages]
        yield TextDelta(text="second answer")
        yield DoneEvent()

    new_user = Message.objects.create(
        thread=t, role="user", content={"text": "follow-up?"}, status="done",
    )

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_run):
        run_ai_on_message.delay(thread_id=t.id, user_message_id=new_user.id).get(timeout=5)

    # Provider received: first user, first assistant, follow-up user (3 total, no system — system is separate)
    roles = [role for role, _ in captured["messages"]]
    assert roles == ["user", "assistant", "user"]
    contents = [content for _, content in captured["messages"]]
    assert contents == ["first question", "first answer", "follow-up?"]
```

- [ ] **Step 9.3: Test + commit**

```bash
docker compose exec web pytest apps/threads/tests/test_chat_history.py -v
git add backend/apps/threads/serializers.py backend/apps/threads/tests/test_chat_history.py
git commit -m "feat(threads): pass full chat history to provider for multi-turn chat mode"
```

Expected: 1 passed. (The task's `_build_request` already handles this — we're just documenting the contract.)

---

## Task 10: Stop streaming message (TDD)

**Files:**
- Modify: `backend/apps/threads/views.py`
- Modify: `backend/apps/threads/models.py` (no change — `AIRun.status="cost_capped"` already covers cancellation; we'll use "failed" with error="cancelled")
- Create: `backend/apps/threads/tests/test_stop.py`

Canceling a mid-flight streaming message is a soft signal — the frontend marks the assistant as failed locally and the backend persists the partial content + status=failed with error="cancelled". We don't need to actually kill the Celery task (it'll finish, write its own AIRun, but see that the message was already marked failed and skip writes).

Simpler approach: endpoint sets `Message.status = "failed"` + `error = "cancelled"` and the task's final transaction checks for this "already cancelled" state and doesn't overwrite.

- [ ] **Step 10.1: Update `backend/apps/threads/tasks.py` — respect a pre-set "failed" status**

Add this near the end of the task, replacing the `with transaction.atomic():` block:

```python
    with transaction.atomic():
        assistant.refresh_from_db()
        if assistant.status == "failed" and assistant.error == "cancelled":
            # User stopped the stream; don't overwrite the cancellation.
            AIRun.objects.create(
                message=assistant, provider=provider_name, model=model_id,
                status="failed", error="cancelled", latency_ms=latency_ms,
                input_tokens=(usage.input_tokens if usage else 0),
                output_tokens=(usage.output_tokens if usage else 0),
            )
            return {"ok": False, "error": "cancelled"}

        if err:
            assistant.content = {"text": "".join(buffer)}
            assistant.status = "failed"
            assistant.error = err
            assistant.save()
            # ... rest unchanged
```

(Apply the edit carefully — keep the existing "err" and "done" branches, just add the cancellation check first.)

- [ ] **Step 10.2: Add stop action to `backend/apps/threads/views.py`**

```python
    @action(detail=True, methods=["post"], url_path=r"stop/(?P<message_id>\d+)")
    def stop(self, request, pk=None, message_id=None):
        """Mark a streaming assistant message as cancelled. Task finishes but skips final write."""
        thread = self.get_object()
        try:
            msg = Message.objects.get(id=message_id, thread=thread, role="assistant")
        except Message.DoesNotExist:
            return Response({"code": "not_found", "message": "Message not found"}, status=404)
        if msg.status != "streaming":
            return Response({"code": "not_streaming", "message": "Message is not streaming"}, status=400)
        msg.status = "failed"
        msg.error = "cancelled"
        msg.save()
        from apps.threads.tasks import _broadcast  # type: ignore[attr-defined]
        _broadcast(thread.id, {"event": "error", "message_id": msg.id, "error": "cancelled"})
        return Response({"ok": True}, status=200)
```

- [ ] **Step 10.3: Write failing test**

Write `backend/apps/threads/tests/test_stop.py`:

```python
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_stop_streaming_message(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="streaming")

    r = api.post(f"/api/threads/{t.id}/stop/{m.id}/", format="json")
    assert r.status_code == 200
    m.refresh_from_db()
    assert m.status == "failed"
    assert m.error == "cancelled"


@pytest.mark.django_db
def test_stop_rejects_non_streaming(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": "ok"}, status="done")

    r = api.post(f"/api/threads/{t.id}/stop/{m.id}/", format="json")
    assert r.status_code == 400
```

- [ ] **Step 10.4: Test + commit**

```bash
docker compose exec web pytest apps/threads/tests/test_stop.py -v
git add backend/apps/threads/tasks.py backend/apps/threads/views.py backend/apps/threads/tests/test_stop.py
git commit -m "feat(threads): stop streaming message endpoint + task respect"
```

Expected: 2 passed.

---

## Task 11: Costs app + endpoints (TDD)

**Files:**
- Create: `backend/apps/costs/__init__.py`, `apps.py`, `services.py`, `urls.py`, `views.py`
- Create: `backend/apps/costs/tests/__init__.py`, `test_costs.py`
- Modify: `backend/config/settings/base.py` — register app
- Modify: `backend/config/urls.py` — mount /api/costs/

- [ ] **Step 11.1: Scaffold**

```bash
mkdir -p /home/dan/ai-dashboard/backend/apps/costs/tests
touch /home/dan/ai-dashboard/backend/apps/costs/__init__.py
touch /home/dan/ai-dashboard/backend/apps/costs/tests/__init__.py
```

Write `backend/apps/costs/apps.py`:

```python
from django.apps import AppConfig


class CostsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.costs"
    label = "costs"
```

Register `"apps.costs",` in `INSTALLED_APPS` after `"apps.ai",`.

- [ ] **Step 11.2: Write failing test**

Write `backend/apps/costs/tests/test_costs.py`:

```python
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.costs.services import cost_breakdown_today
from apps.profiles.models import TradingProfile
from apps.threads.models import AIRun, Message, Thread


@pytest.mark.django_db
def test_cost_breakdown_today_aggregates_by_provider():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m1 = Message.objects.create(thread=t, role="assistant", content={"text": "a"}, status="done")
    m2 = Message.objects.create(thread=t, role="assistant", content={"text": "b"}, status="done")
    m3 = Message.objects.create(thread=t, role="assistant", content={"text": "c"}, status="done")
    AIRun.objects.create(message=m1, provider="claude", model="claude-sonnet-4-6",
                         cost_usd=Decimal("0.0100"), status="done",
                         input_tokens=1000, output_tokens=500)
    AIRun.objects.create(message=m2, provider="claude", model="claude-sonnet-4-6",
                         cost_usd=Decimal("0.0200"), status="done",
                         input_tokens=2000, output_tokens=1000)
    AIRun.objects.create(message=m3, provider="openai", model="gpt-5",
                         cost_usd=Decimal("0.0300"), status="done",
                         input_tokens=500, output_tokens=200)

    out = cost_breakdown_today()
    assert out["total_usd"] == Decimal("0.0600")
    claude = next(p for p in out["by_provider"] if p["provider"] == "claude")
    assert claude["cost_usd"] == Decimal("0.0300")
    assert claude["input_tokens"] == 3000
    assert claude["output_tokens"] == 1500
    assert claude["runs"] == 2
    openai = next(p for p in out["by_provider"] if p["provider"] == "openai")
    assert openai["cost_usd"] == Decimal("0.0300")
    assert openai["runs"] == 1
```

- [ ] **Step 11.3: Write `backend/apps/costs/services.py`**

```python
"""Cost aggregation helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from django.db.models import Count, Sum

from apps.threads.models import AIRun


def cost_breakdown_today() -> dict:
    start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    qs = AIRun.objects.filter(created_at__gte=start)
    by_provider = list(
        qs.values("provider").annotate(
            cost_usd=Sum("cost_usd"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cached_tokens=Sum("cached_tokens"),
            runs=Count("id"),
        ).order_by("provider")
    )
    # Django Sum over Decimal returns Decimal(0) when no rows — OK.
    total = sum((row["cost_usd"] or Decimal("0")) for row in by_provider)
    return {
        "total_usd": total or Decimal("0"),
        "by_provider": [
            {
                "provider": row["provider"],
                "cost_usd": row["cost_usd"] or Decimal("0"),
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "cached_tokens": row["cached_tokens"] or 0,
                "runs": row["runs"],
            }
            for row in by_provider
        ],
    }
```

- [ ] **Step 11.4: Write `views.py` + `urls.py`**

Write `backend/apps/costs/views.py`:

```python
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.costs.services import cost_breakdown_today


@require_GET
def costs_today(_request: HttpRequest) -> JsonResponse:
    out = cost_breakdown_today()
    return JsonResponse({
        "total_usd": str(out["total_usd"]),
        "by_provider": [
            {
                "provider": row["provider"],
                "cost_usd": str(row["cost_usd"]),
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cached_tokens": row["cached_tokens"],
                "runs": row["runs"],
            }
            for row in out["by_provider"]
        ],
    })
```

Write `backend/apps/costs/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("today/", views.costs_today, name="costs-today"),
]
```

Edit `backend/config/urls.py` to add:

```python
    path("api/costs/", include("apps.costs.urls")),
```

- [ ] **Step 11.5: Test + commit**

```bash
docker compose exec web python manage.py migrate  # costs has no models but registering it is good practice
docker compose exec web pytest apps/costs/tests/test_costs.py -v
git add backend/apps/costs backend/config/settings/base.py backend/config/urls.py
git commit -m "feat(costs): /api/costs/today endpoint with per-provider breakdown"
```

Expected: 1 passed.

---

## Task 12: Frontend — provider+model picker + compare + stop + costs

**Files:**
- Create: `frontend/src/api/costs.ts`
- Create: `frontend/src/hooks/useCosts.ts`
- Modify: `frontend/src/api/threads.ts` — add `compareMessage` + `stopMessage`
- Modify: `frontend/src/hooks/useThread.ts` — add `useCompareMessage`, `useStopMessage`
- Create: `frontend/src/components/ProviderModelPicker.tsx`
- Create: `frontend/src/components/CompareDialog.tsx`
- Create: `frontend/src/components/BranchTabs.tsx`
- Create: `frontend/src/components/StopButton.tsx`
- Create: `frontend/src/components/CostChip.tsx`
- Modify: `frontend/src/pages/ThreadDetailPage.tsx`
- Create: `frontend/src/pages/CostsPage.tsx`
- Modify: `frontend/src/router.tsx` — add /costs
- Modify: `frontend/src/pages/Dashboard.tsx` — add costs chip + link

- [ ] **Step 12.1: api + hooks**

Write `frontend/src/api/costs.ts`:

```ts
import { apiGet } from "./client";

export type ProviderCost = {
  provider: string; cost_usd: string; runs: number;
  input_tokens: number; output_tokens: number; cached_tokens: number;
};
export type CostsToday = { total_usd: string; by_provider: ProviderCost[] };

export const fetchCostsToday = () => apiGet<CostsToday>("/api/costs/today/");
```

Write `frontend/src/hooks/useCosts.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchCostsToday } from "@/api/costs";

export const useCostsToday = () =>
  useQuery({ queryKey: ["costs-today"], queryFn: fetchCostsToday, refetchInterval: 30_000 });
```

Edit `frontend/src/api/threads.ts` — add:

```ts
export const compareMessage = (threadId: number, text: string, branches: {provider: string; model: string}[]) =>
  apiPost<{ user_message_id: number; branches: { provider: string; model: string; task_id: string }[] }>(
    `/api/threads/${threadId}/compare/`, { text, branches },
  );

export const stopMessage = (threadId: number, messageId: number) =>
  apiPost<{ ok: boolean }>(`/api/threads/${threadId}/stop/${messageId}/`);
```

Edit `frontend/src/hooks/useThread.ts` — add:

```ts
import { compareMessage, stopMessage } from "@/api/threads";

export function useCompareMessage(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { text: string; branches: {provider: string; model: string}[] }) =>
      compareMessage(threadId, args.text, args.branches),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}

export function useStopMessage(threadId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (messageId: number) => stopMessage(threadId, messageId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thread", threadId] }),
  });
}
```

- [ ] **Step 12.2: Components**

Write `frontend/src/components/ProviderModelPicker.tsx`:

```tsx
import { useAiModels } from "@/hooks/useAiModels";

type Value = { provider: string; model: string };
type Props = { value: Value; onChange: (v: Value) => void };

export default function ProviderModelPicker({ value, onChange }: Props) {
  const { data } = useAiModels();
  const all = data?.models ?? [];
  const providers = Array.from(new Set(all.map((m) => m.provider)));
  const modelsForProvider = all.filter((m) => m.provider === value.provider);

  return (
    <div className="flex gap-2 text-sm">
      <select
        value={value.provider}
        onChange={(e) => {
          const provider = e.target.value;
          const firstModel = all.find((m) => m.provider === provider)?.id ?? "";
          onChange({ provider, model: firstModel });
        }}
        className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
      >
        {providers.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <select
        value={value.model}
        onChange={(e) => onChange({ ...value, model: e.target.value })}
        className="flex-1 px-2 py-1 rounded bg-slate-900 border border-slate-700"
      >
        {modelsForProvider.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        {modelsForProvider.length === 0 && (
          <option value="">(no catalog models — type your own)</option>
        )}
      </select>
    </div>
  );
}
```

Write `frontend/src/components/CompareDialog.tsx`:

```tsx
import { useState } from "react";
import ProviderModelPicker from "./ProviderModelPicker";

type Branch = { provider: string; model: string };
type Props = {
  onCancel: () => void;
  onSubmit: (text: string, branches: Branch[]) => void;
};

export default function CompareDialog({ onCancel, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [branches, setBranches] = useState<Branch[]>([
    { provider: "claude", model: "claude-sonnet-4-6" },
    { provider: "openai", model: "gpt-5-mini" },
  ]);

  return (
    <div className="fixed inset-0 bg-black/70 grid place-items-center z-50">
      <div className="bg-slate-950 border border-slate-700 rounded p-4 max-w-xl w-full space-y-3">
        <h2 className="text-lg font-medium">Compare across providers</h2>
        <textarea
          rows={3} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Message to send to each branch…"
          className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
        />
        {branches.map((b, i) => (
          <div key={i} className="flex items-center gap-2">
            <ProviderModelPicker value={b} onChange={(v) => {
              const next = [...branches]; next[i] = v; setBranches(next);
            }} />
            {branches.length > 1 && (
              <button className="text-xs text-rose-400 hover:underline"
                      onClick={() => setBranches(branches.filter((_, j) => j !== i))}>
                remove
              </button>
            )}
          </div>
        ))}
        <div className="flex justify-between">
          <button className="text-sm text-slate-300 hover:underline"
                  onClick={() => setBranches([...branches, { provider: "claude", model: "claude-sonnet-4-6" }])}>
            + branch
          </button>
          <div className="flex gap-2">
            <button onClick={onCancel} className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-sm">
              Cancel
            </button>
            <button
              onClick={() => { if (text.trim() && branches.length) onSubmit(text.trim(), branches); }}
              className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-sm"
            >
              Send to {branches.length} branches
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

Write `frontend/src/components/BranchTabs.tsx`:

```tsx
type Props = {
  branches: { id: number; label: string; status: "streaming" | "done" | "failed" }[];
  activeId: number | null;
  onSelect: (id: number) => void;
};

export default function BranchTabs({ branches, activeId, onSelect }: Props) {
  if (branches.length <= 1) return null;
  return (
    <div className="flex gap-1 border-b border-slate-800 text-xs">
      {branches.map((b) => (
        <button
          key={b.id}
          onClick={() => onSelect(b.id)}
          className={`px-3 py-1.5 border-b-2 ${
            activeId === b.id ? "border-emerald-500 text-emerald-300" : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          {b.label}
          <span className="ml-1 text-slate-600">
            {b.status === "streaming" ? "…" : b.status === "failed" ? "✗" : ""}
          </span>
        </button>
      ))}
    </div>
  );
}
```

Write `frontend/src/components/StopButton.tsx`:

```tsx
type Props = { onStop: () => void };

export default function StopButton({ onStop }: Props) {
  return (
    <button
      onClick={onStop}
      className="text-xs px-2 py-0.5 rounded bg-rose-900/40 text-rose-200 hover:bg-rose-900/60"
    >
      Stop
    </button>
  );
}
```

Write `frontend/src/components/CostChip.tsx`:

```tsx
import { Link } from "react-router-dom";
import { useCostsToday } from "@/hooks/useCosts";

export default function CostChip() {
  const { data } = useCostsToday();
  const total = Number(data?.total_usd ?? "0");
  return (
    <Link to="/costs" className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300">
      today: ${total.toFixed(4)}
    </Link>
  );
}
```

- [ ] **Step 12.3: Costs page**

Write `frontend/src/pages/CostsPage.tsx`:

```tsx
import { useCostsToday } from "@/hooks/useCosts";

export default function CostsPage() {
  const { data, isLoading } = useCostsToday();
  if (isLoading) return <main className="p-6">Loading…</main>;

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Costs — today</h1>
      <div className="text-3xl tabular-nums">
        ${Number(data?.total_usd ?? "0").toFixed(4)}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-slate-400 text-left">
            <th className="py-2">Provider</th>
            <th className="py-2">Runs</th>
            <th className="py-2">Input tok</th>
            <th className="py-2">Cached</th>
            <th className="py-2">Output tok</th>
            <th className="py-2">Cost</th>
          </tr>
        </thead>
        <tbody>
          {(data?.by_provider ?? []).map((p) => (
            <tr key={p.provider} className="border-t border-slate-800">
              <td className="py-2 capitalize font-medium">{p.provider}</td>
              <td className="py-2 tabular-nums">{p.runs}</td>
              <td className="py-2 tabular-nums">{p.input_tokens.toLocaleString()}</td>
              <td className="py-2 tabular-nums text-slate-500">{p.cached_tokens.toLocaleString()}</td>
              <td className="py-2 tabular-nums">{p.output_tokens.toLocaleString()}</td>
              <td className="py-2 tabular-nums">${Number(p.cost_usd).toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
```

- [ ] **Step 12.4: Update ThreadDetailPage — integrate picker + compare + stop + branches**

Replace `frontend/src/pages/ThreadDetailPage.tsx` with:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import BranchTabs from "@/components/BranchTabs";
import CompareDialog from "@/components/CompareDialog";
import ProviderModelPicker from "@/components/ProviderModelPicker";
import StopButton from "@/components/StopButton";
import StreamingMessage from "@/components/StreamingMessage";
import { useChannel } from "@/hooks/useChannel";
import { useSnapshot } from "@/hooks/useSnapshot";
import { useCompareMessage, useSendMessage, useStopMessage, useThread } from "@/hooks/useThread";

type LiveMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  status: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
  provider?: string;
  parent_message_id?: number | null;
};

export default function ThreadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [search] = useSearchParams();
  const tid = id ? parseInt(id, 10) : null;
  const snapshotId = search.get("snapshot") ? parseInt(search.get("snapshot")!, 10) : null;

  const { data: thread, refetch } = useThread(tid);
  const { data: snap } = useSnapshot(snapshotId);

  const [live, setLive] = useState<Record<number, LiveMessage>>({});
  const [activeBranchByParent, setActiveBranchByParent] = useState<Record<number, number>>({});
  const [picker, setPicker] = useState({ provider: "claude", model: "claude-sonnet-4-6" });
  const [showCompare, setShowCompare] = useState(false);

  useEffect(() => {
    if (!thread) return;
    const seed: Record<number, LiveMessage> = {};
    for (const m of thread.messages) {
      seed[m.id] = {
        id: m.id,
        role: m.role === "system" ? "assistant" : m.role,
        text: m.content?.text ?? "",
        status: m.status,
        error: m.error,
        cost: m.ai_run?.cost_usd,
        model: m.ai_run?.model,
        provider: m.ai_run?.provider,
        parent_message_id: (m as any).parent_message_id ?? null,
      };
    }
    setLive(seed);
  }, [thread]);

  const onWs = useCallback((msg: any) => {
    if (msg.event === "message_started") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: {
          id: msg.message_id, role: "assistant", text: "", status: "streaming",
          model: msg.model, provider: msg.provider,
          parent_message_id: msg.parent_message_id ?? null,
        },
      }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[msg.message_id] ?? {
          id: msg.message_id, role: "assistant" as const, text: "", status: "streaming" as const,
        };
        return { ...prev, [msg.message_id]: { ...cur, text: cur.text + msg.text } };
      });
    } else if (msg.event === "message_done") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "done", cost: msg.cost_usd },
      }));
      refetch();
    } else if (msg.event === "error" || msg.event === "cost_capped") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "failed", error: msg.error },
      }));
    }
  }, [refetch]);

  useChannel(tid ? `thread.${tid}` : null, onWs);

  const send = useSendMessage(tid ?? 0);
  const compare = useCompareMessage(tid ?? 0);
  const stop = useStopMessage(tid ?? 0);
  const [input, setInput] = useState("");

  // Group assistant branches by parent_message_id; user messages render standalone.
  const { ordered, branchesByParent } = useMemo(() => {
    const arr = Object.values(live).sort((a, b) => a.id - b.id);
    const byParent: Record<number, LiveMessage[]> = {};
    const top: LiveMessage[] = [];
    for (const m of arr) {
      if (m.role === "assistant" && m.parent_message_id != null) {
        (byParent[m.parent_message_id] ??= []).push(m);
      } else {
        top.push(m);
      }
    }
    return { ordered: top, branchesByParent: byParent };
  }, [live]);

  if (!thread) return <main className="p-6">Loading…</main>;

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">{thread.title || `Thread #${thread.id}`}</h1>
        <Link to="/" className="text-sm text-slate-300 hover:underline">← Dashboard</Link>
      </div>

      {snap && (
        <details className="p-3 rounded border border-slate-800">
          <summary className="cursor-pointer text-sm text-slate-300">
            Snapshot #{snap.id} · {snap.status} · {snap.includes.join(", ")}
          </summary>
          <pre className="mt-2 text-xs text-slate-400 overflow-x-auto">
            {JSON.stringify(snap.sections.map((s) => ({ kind: s.kind, status: s.status, error: s.error })), null, 2)}
          </pre>
        </details>
      )}

      <section className="space-y-3">
        {ordered.map((m) => {
          if (m.role === "user") {
            const children = branchesByParent[m.id] ?? [];
            const activeId = activeBranchByParent[m.id] ?? children[0]?.id ?? null;
            const active = children.find((c) => c.id === activeId) ?? children[0];
            return (
              <div key={m.id} className="space-y-2">
                <StreamingMessage role="user" text={m.text} status={m.status} />
                {children.length > 0 && (
                  <>
                    <BranchTabs
                      branches={children.map((c) => ({
                        id: c.id,
                        label: `${c.provider ?? "?"} / ${c.model ?? "?"}`,
                        status: c.status,
                      }))}
                      activeId={activeId}
                      onSelect={(cid) => setActiveBranchByParent((s) => ({ ...s, [m.id]: cid }))}
                    />
                    {active && (
                      <div className="flex items-start gap-2">
                        <div className="flex-1">
                          <StreamingMessage
                            role={active.role} text={active.text} status={active.status}
                            error={active.error} cost={active.cost} model={active.model}
                          />
                        </div>
                        {active.status === "streaming" && (
                          <StopButton onStop={() => stop.mutate(active.id)} />
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          }
          // Top-level assistant (no parent) — used for the initial consult reply.
          return (
            <div key={m.id} className="flex items-start gap-2">
              <div className="flex-1">
                <StreamingMessage
                  role={m.role} text={m.text} status={m.status}
                  error={m.error} cost={m.cost} model={m.model}
                />
              </div>
              {m.status === "streaming" && <StopButton onStop={() => stop.mutate(m.id)} />}
            </div>
          );
        })}
      </section>

      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>Reply with:</span>
          <ProviderModelPicker value={picker} onChange={setPicker} />
          <button
            className="ml-auto px-2 py-1 rounded bg-slate-800 hover:bg-slate-700"
            onClick={() => setShowCompare(true)}
          >
            Compare…
          </button>
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!input.trim()) return;
            send.mutate(input.trim(), { onSuccess: () => setInput("") });
          }}
        >
          <input
            value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="Message"
            className="flex-1 px-3 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
          <button className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500">Send</button>
        </form>
      </div>

      {showCompare && (
        <CompareDialog
          onCancel={() => setShowCompare(false)}
          onSubmit={(text, branches) => {
            compare.mutate({ text, branches });
            setShowCompare(false);
          }}
        />
      )}
    </main>
  );
}
```

Note: `useSendMessage` currently doesn't pass an override. The picker's value is currently informational — hooking the provider override into the normal send is a small improvement; for now, plain Send uses the profile default. Compare uses the dialog's branches. M5 can unify.

- [ ] **Step 12.5: Add /costs route + Dashboard chip**

Edit `frontend/src/router.tsx`:

```tsx
import CostsPage from "./pages/CostsPage";
// ...
  { path: "/costs", element: <CostsPage /> },
```

Edit `frontend/src/pages/Dashboard.tsx` nav:

```tsx
import CostChip from "@/components/CostChip";
// ...
        <nav className="text-sm space-x-4 flex items-center">
          <CostChip />
          <Link className="text-slate-300 hover:underline" to="/profiles">Profiles</Link>
          <Link className="text-slate-300 hover:underline" to="/watchlists">Watchlists</Link>
          <Link className="text-slate-300 hover:underline" to="/threads">Threads</Link>
          <Link className="text-slate-300 hover:underline" to="/settings">Settings</Link>
          <Link className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white" to="/snapshot">
            + Snapshot
          </Link>
        </nav>
```

- [ ] **Step 12.6: Test + commit**

```bash
docker compose exec frontend npm test -- --run
git add frontend/src
git commit -m "feat(frontend): provider picker + compare dialog + stop + branch tabs + costs page + chip"
```

Expected: existing tests still pass (9). No new frontend tests — these are mostly UI plumbing; logic is covered by backend tests.

---

## Task 13: Full test + lint pass

- [ ] **Step 13.1: Run full backend suite**

```bash
cd /home/dan/ai-dashboard
docker compose exec web pytest -v
```

Expected: all M1 + M2 + M3 + M4 tests pass. Should be ~120 tests.

- [ ] **Step 13.2: Frontend suite**

```bash
docker compose exec frontend npm test -- --run
```

Expected: 9 passed.

- [ ] **Step 13.3: Lint**

```bash
make lint
```

Expected: zero errors. Fix if any. Common issues for M4:
- TS `any` parameter annotations in new components — annotate with types from `@/api/*`.
- Ruff unused imports in refactored `tasks.py`.
- Mypy complaints about Union returns from `_build_request` — add casts as needed.

- [ ] **Step 13.4: Commit fixes**

```bash
git add -u
git commit -m "chore: M4 lint fixes" || echo "nothing to commit"
```

---

## Task 14: E2E smoke

- [ ] **Step 14.1: Confirm all endpoints**

```bash
cd /home/dan/ai-dashboard

# Providers CRUD works (from M3)
curl -s http://localhost:8000/api/schwab/providers/ | head -c 200
echo

# AI models now lists openai entries
curl -s "http://localhost:8000/api/schwab/models/?provider=openai" | head -c 400
echo

# Costs today
curl -s http://localhost:8000/api/costs/today/ | head -c 200
echo

# UI pages
for path in "/" "/profiles" "/snapshot" "/threads" "/settings" "/watchlists" "/costs"; do
  printf "%-15s " "$path"
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173$path
done
```

Expected:
- `/api/schwab/models/?provider=openai` returns gpt-5, gpt-5-mini, gpt-5-nano.
- `/api/costs/today/` returns `{total_usd: "0", by_provider: []}` (no runs today in a fresh DB).
- All UI pages return 200.

- [ ] **Step 14.2: Optional — compare path smoke**

Requires a real profile + 2 configured providers. Skip unless the user has real keys.

---

## Task 15: Cold rebuild + tag m4

- [ ] **Step 15.1: Cold rebuild**

```bash
cd /home/dan/ai-dashboard
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 45
curl -s http://localhost:8000/api/health/
curl -s http://localhost:8000/api/ready/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/
docker compose exec web pytest -q 2>&1 | tail -5
docker compose exec frontend npm test -- --run 2>&1 | tail -8
```

Expected: all green.

- [ ] **Step 15.2: Tag**

```bash
git add -u
git commit -m "chore: M4 full threads verified" || echo "nothing"
git tag -a m4-full-threads -m "M4: OpenAI + Local providers, multi-turn chat, compare, costs page, stop"
git log --oneline -10
git tag -l
```

## Done

Next: **M5 — Option chains + news + images** (OptionChain model + chain view + Finnhub/Marketaux news ingestion + client screenshot + Playwright server-side chart render).
