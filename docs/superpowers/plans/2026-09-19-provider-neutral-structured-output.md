# Provider-Neutral Structured Output + Catalog Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one-shot structured output work for Claude, OpenAI, and Local behind one facade so every self-measurement path (ledger, eval, consensus, War Room verdict, narratives) can run on any configured provider, and refresh the model catalog with current models and verified prices.

**Architecture:** A new public module `apps/ai/structured.py` dispatches `run_structured(provider=...)` to the existing Anthropic implementation or a new OpenAI-compatible one, and owns target resolution (override → profile → calibration → first enabled). The eight callers switch their import to the facade and pass the provider they already know or resolve via the facade. The catalog gains five current models, corrected prices for four stale rows, and a per-provider default.

**Tech Stack:** Django 5 / DRF, Celery, Pydantic v2, `anthropic` 0.104 (`messages.parse`), `openai` 2.38 (`chat.completions.parse`), pytest-django, import-linter, mypy (zero baseline), ruff.

**Spec:** `docs/superpowers/specs/2026-09-19-provider-neutral-structured-output-design.md`

## Global Constraints

- Work happens in the worktree `/home/dan/ledger/.claude/worktrees/provider-neutral-structured-output` on branch `worktree-provider-neutral-structured-output`. Never `cd` to `/home/dan/ledger`.
- The dev stack runs from the main checkout under project `ai-dashboard`. Tests and lint run against the worktree through a compose override. Define once per shell:
  ```bash
  WT=/home/dan/ledger/.claude/worktrees/provider-neutral-structured-output
  OVR=/tmp/claude-1000/-home-dan-ledger/28e4fe18-1309-45f6-bf71-c618b9253ad8/scratchpad/wt-override.yaml
  RUN="docker compose -f /home/dan/ledger/compose.yaml -f $OVR run --rm --no-deps"
  PYTEST="$RUN web uv run pytest -p no:randomly -q --no-header"
  ```
  Test paths are given relative to `/app/backend` (container WORKDIR), e.g. `$PYTEST apps/ai/tests/test_catalog.py`.
- The host has no `lefthook`; commit with `LEFTHOOK=0 git commit ...`. Every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Code comments and docstrings are present-tense invariants. No "was", "legacy", "now supports", milestone tags, or origin stories.
- No `MOCK_EXTERNAL` short-circuit in structured paths; tests patch the SDK client class.
- `ruff C901` complexity ≤ 15; no `assert` in shipped code; never log an API key.
- Model ids and prices come from the spec §2 table verbatim.
- Old catalog rows keep their ids and payload budgets.

---

### Task 1: Catalog refresh

**Files:**
- Modify: `backend/apps/ai/catalog.py` (whole file)
- Test: `backend/apps/ai/tests/test_catalog.py`, `backend/apps/ai/tests/test_catalog_openai.py`, `backend/apps/ai/tests/test_cost.py:39-66`

**Interfaces:**
- Produces: `DEFAULT_CLAUDE_MODEL = "claude-opus-5"`, `DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"`, `default_model_for(provider: str) -> str`, and catalog rows for `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5`, `gpt-6-astra`, `gpt-5.6-sol`. `CLAUDE_FAMILY_PROVIDERS`, `ModelInfo`, `list_models`, `get_model`, `ceiling_for_provider` unchanged in signature.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/ai/tests/test_catalog.py`:

```python
import pytest

from apps.ai.catalog import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_OPENAI_MODEL,
    default_model_for,
)


def test_current_generation_models_present():
    claude_ids = {m.id for m in list_models("claude")}
    assert {"claude-fable-5-1", "claude-opus-5", "claude-sonnet-5"} <= claude_ids
    openai_ids = {m.id for m in list_models("openai")}
    assert {"gpt-6-astra", "gpt-5.6-sol"} <= openai_ids


@pytest.mark.parametrize(
    ("provider", "model_id", "inp", "cached", "out", "ctx"),
    [
        ("claude", "claude-fable-5-1", 10.00, 0.25, 50.00, 1_000_000),
        ("claude", "claude-opus-5", 5.00, 0.50, 25.00, 1_000_000),
        ("claude", "claude-sonnet-5", 2.00, 0.20, 10.00, 1_000_000),
        ("claude", "claude-opus-4-8", 5.00, 0.50, 25.00, 1_000_000),
        ("claude", "claude-sonnet-4-6", 3.00, 0.375, 15.00, 1_000_000),
        ("openai", "gpt-6-astra", 10.00, 1.00, 50.00, 1_050_000),
        ("openai", "gpt-5.6-sol", 4.00, 0.40, 20.00, 1_050_000),
        ("openai", "gpt-5", 1.25, 0.125, 10.00, 400_000),
        ("openai", "gpt-5-mini", 0.25, 0.025, 2.00, 400_000),
        ("openai", "gpt-5-nano", 0.05, 0.005, 0.40, 400_000),
    ],
)
def test_verified_pricing_and_context(provider, model_id, inp, cached, out, ctx):
    m = get_model(provider, model_id)
    assert m is not None
    assert (m.input_per_mtok, m.cached_per_mtok, m.output_per_mtok, m.context_window) == (
        inp,
        cached,
        out,
        ctx,
    )


def test_default_model_for_each_provider():
    assert DEFAULT_CLAUDE_MODEL == "claude-opus-5"
    assert DEFAULT_OPENAI_MODEL == "gpt-5.6-sol"
    assert default_model_for("claude") == "claude-opus-5"
    assert default_model_for("anthropic") == "claude-opus-5"
    assert default_model_for("openai") == "gpt-5.6-sol"
    assert default_model_for("local") == ""
    assert default_model_for("nonexistent") == ""


def test_defaults_are_catalog_rows():
    assert get_model("claude", DEFAULT_CLAUDE_MODEL) is not None
    assert get_model("openai", DEFAULT_OPENAI_MODEL) is not None
```

In the same file, change the ceiling assertions in `test_ceiling_for_provider_is_scoped_to_that_provider`:

```python
    assert openai_ceiling.id == "gpt-6-astra"
    ...
    assert claude_ceiling.id == "claude-fable-5-1"
```

In `backend/apps/ai/tests/test_cost.py` replace the last two tests' expectations:

```python
def test_cost_for_unknown_model_uses_provider_ceiling():
    # Claude's ceiling is Fable 5.1 ($10 in / $50 out per Mtok): 1k + 1k tokens = $0.06.
    usage = TokenUsage(input_tokens=1000, output_tokens=1000)
    cost = cost_usd_for("claude", "claude-made-up-model", usage)
    assert cost == Decimal("0.060000")
```

```python
def test_cost_unknown_model_prices_off_provider_ceiling_not_global_max():
    # openai's ceiling is gpt-6-astra ($10 in / $50 out per Mtok). An unknown openai
    # model must be priced off openai's own ceiling, not whichever model tops the
    # whole catalog.
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = cost_usd_for("openai", "made-up-openai-model", usage)
    assert cost == Decimal("60.000000")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PYTEST apps/ai/tests/test_catalog.py apps/ai/tests/test_catalog_openai.py apps/ai/tests/test_cost.py`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_OPENAI_MODEL'` and the ceiling/cost assertions.

- [ ] **Step 3: Replace `backend/apps/ai/catalog.py` with the refreshed catalog**

```python
"""Model catalog with per-model pricing. Source of truth for cost estimation and
per-model snapshot payload budgets.

Prices are USD per 1M tokens as published on each vendor's model page. Update
when providers revise.
"""

from __future__ import annotations

from dataclasses import dataclass

# Provider names that resolve to Anthropic endpoints. Anthropic-only paths
# (Messages Batches) must check membership before wrapping an arbitrary
# ProviderConfig in an Anthropic client — sending another vendor's key to
# api.anthropic.com fails every call with an opaque 401.
CLAUDE_FAMILY_PROVIDERS = ("claude", "anthropic")

# Fallback model per provider for best-effort / structured paths when no per-send
# or profile/schedule override and no ProviderConfig.default_model is set.
# Single source of truth — bump here, not in each caller.
DEFAULT_CLAUDE_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"


def default_model_for(provider: str) -> str:
    """The catalog fallback model for ``provider``; ``""`` for ``local`` (its models
    are user-declared, never assumed) and for unknown providers."""
    if provider in CLAUDE_FAMILY_PROVIDERS:
        return DEFAULT_CLAUDE_MODEL
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    return ""


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    id: str
    name: str
    input_per_mtok: float
    output_per_mtok: float
    cached_per_mtok: float
    context_window: int
    supports_vision: bool
    max_payload_tokens: int = 40_000


_CATALOG: list[ModelInfo] = [
    ModelInfo(
        provider="claude",
        id="claude-fable-5-1",
        name="Claude Fable 5.1",
        input_per_mtok=10.00,
        output_per_mtok=50.00,
        cached_per_mtok=0.25,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-opus-5",
        name="Claude Opus 5",
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        cached_per_mtok=0.50,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-sonnet-5",
        name="Claude Sonnet 5",
        input_per_mtok=2.00,
        output_per_mtok=10.00,
        cached_per_mtok=0.20,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-opus-4-8",
        name="Claude Opus 4.8",
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        cached_per_mtok=0.50,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-sonnet-4-6",
        name="Claude Sonnet 4.6",
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_per_mtok=0.375,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-haiku-4-5-20251001",
        name="Claude Haiku 4.5",
        input_per_mtok=1.00,
        output_per_mtok=5.00,
        cached_per_mtok=0.125,
        context_window=200_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-6-astra",
        name="GPT-6 Astra",
        input_per_mtok=10.00,
        output_per_mtok=50.00,
        cached_per_mtok=1.00,
        context_window=1_050_000,
        supports_vision=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5.6-sol",
        name="GPT-5.6 Sol",
        input_per_mtok=4.00,
        output_per_mtok=20.00,
        cached_per_mtok=0.40,
        context_window=1_050_000,
        supports_vision=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5",
        name="GPT-5",
        input_per_mtok=1.25,
        output_per_mtok=10.00,
        cached_per_mtok=0.125,
        context_window=400_000,
        supports_vision=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5-mini",
        name="GPT-5 Mini",
        input_per_mtok=0.25,
        output_per_mtok=2.00,
        cached_per_mtok=0.025,
        context_window=400_000,
        supports_vision=True,
        max_payload_tokens=200_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5-nano",
        name="GPT-5 Nano",
        input_per_mtok=0.05,
        output_per_mtok=0.40,
        cached_per_mtok=0.005,
        context_window=400_000,
        supports_vision=False,
        max_payload_tokens=200_000,
    ),
]


def list_models(provider: str | None = None) -> list[ModelInfo]:
    if provider is None:
        return list(_CATALOG)
    return [m for m in _CATALOG if m.provider == provider]


def get_model(provider: str, model_id: str) -> ModelInfo | None:
    for m in _CATALOG:
        if m.provider == provider and m.id == model_id:
            return m
    return None


def ceiling_for_provider(provider: str) -> ModelInfo | None:
    entries = list_models(provider)
    if not entries:
        return None
    return max(entries, key=lambda m: m.output_per_mtok)
```

- [ ] **Step 4: Run the catalog, cost, and every test that touches pricing**

Run: `$PYTEST apps/ai apps/observer/tests/test_batch.py apps/analytics/tests/test_leaderboard.py`
Expected: PASS. If a test elsewhere hard-codes an old price, fix the test's expected value to the new catalog row (the row is the source of truth), never the catalog.

- [ ] **Step 5: Commit**

```bash
cd $WT && git add backend/apps/ai/catalog.py backend/apps/ai/tests/test_catalog.py backend/apps/ai/tests/test_cost.py
LEFTHOOK=0 git commit -m "feat(ai): refresh model catalog with current models, verified prices, per-provider defaults

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: OpenAI-compatible structured implementation

**Files:**
- Create: `backend/apps/ai/providers/openai_structured.py`
- Test: `backend/apps/ai/tests/test_openai_structured.py` (new)

**Interfaces:**
- Consumes: `apps.ai.providers.claude_structured.StructuredParseError`, `apps.ai.providers._config.client_kwargs`, `apps.ai.cost.record_ai_run(provider, model, usage, latency_ms)`, `apps.ai.types.TokenUsage(input_tokens, output_tokens, cached_tokens, cache_write_tokens)`.
- Produces: `run_structured(*, provider, api_key, model, system, user, output_model, max_tokens=2048, base_url="") -> M` and `token_usage_from_openai(usage) -> TokenUsage`.

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/ai/tests/test_openai_structured.py`:

```python
"""Structured runs against OpenAI-compatible endpoints: strict-schema parse for
``openai``, the same plus a ``json_object`` fallback for ``local``, and an
``AIRun`` recorded under the real provider so cost caps see the spend.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import BadRequestError
from pydantic import BaseModel

pytestmark = pytest.mark.django_db

MOD = "apps.ai.providers.openai_structured"


class _Out(BaseModel):
    summary: str


def _usage(prompt=1000, completion=200, cached=0):
    usage = MagicMock()
    usage.prompt_tokens = prompt
    usage.completion_tokens = completion
    usage.prompt_tokens_details = MagicMock()
    usage.prompt_tokens_details.cached_tokens = cached
    return usage


def _completion(*, parsed=_Out(summary="ok"), refusal=None, content=None, **usage_kw):
    message = MagicMock()
    message.parsed = parsed
    message.refusal = refusal
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = _usage(**usage_kw)
    return completion


def _bad_request() -> BadRequestError:
    request = httpx.Request("POST", "http://local/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError("unsupported response_format", response=response, body=None)


def _run(*, provider="openai", client=None, **overrides):
    from apps.ai.providers.openai_structured import run_structured

    fake_client = client or MagicMock()
    if client is None:
        fake_client.chat.completions.parse.return_value = _completion()
    kwargs = dict(
        provider=provider,
        api_key="sk-test",
        model="gpt-5.6-sol",
        system="sys",
        user="hi",
        output_model=_Out,
    )
    kwargs.update(overrides)
    with patch(f"{MOD}.OpenAI", return_value=fake_client) as ctor:
        result = run_structured(**kwargs)
    return result, fake_client, ctor


def test_openai_parse_records_airun_with_cost():
    from apps.threads.models import AIRun

    out, _client, _ctor = _run()

    assert out.summary == "ok"
    run = AIRun.objects.get()
    assert run.provider == "openai"
    assert run.model == "gpt-5.6-sol"
    assert run.input_tokens == 1000
    assert run.output_tokens == 200
    assert run.cost_usd > Decimal("0")


def test_local_records_airun_at_zero_cost():
    from apps.threads.models import AIRun

    _run(provider="local", base_url="http://host.docker.internal:11434/v1", model="llama")

    run = AIRun.objects.get()
    assert run.provider == "local"
    assert run.cost_usd == Decimal("0")


def test_refusal_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.parse.return_value = _completion(parsed=None, refusal="no")
    with pytest.raises(StructuredParseError, match="refused"):
        _run(client=client)


def test_missing_parsed_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.parse.return_value = _completion(parsed=None)
    with pytest.raises(StructuredParseError):
        _run(client=client)


def test_openai_uses_max_completion_tokens():
    _out, client, _ctor = _run(max_tokens=777)
    kw = client.chat.completions.parse.call_args.kwargs
    assert kw["max_completion_tokens"] == 777
    assert "max_tokens" not in kw
    assert kw["response_format"] is _Out
    assert kw["model"] == "gpt-5.6-sol"


def test_local_uses_max_tokens():
    _out, client, _ctor = _run(provider="local", base_url="http://x/v1", max_tokens=555)
    kw = client.chat.completions.parse.call_args.kwargs
    assert kw["max_tokens"] == 555
    assert "max_completion_tokens" not in kw


def test_system_message_precedes_user_and_is_omitted_when_empty():
    _out, client, _ctor = _run(system="be terse")
    msgs = client.chat.completions.parse.call_args.kwargs["messages"]
    assert msgs == [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]

    _out, client, _ctor = _run(system="")
    msgs = client.chat.completions.parse.call_args.kwargs["messages"]
    assert msgs == [{"role": "user", "content": "hi"}]


def test_local_falls_back_to_json_object_on_400():
    client = MagicMock()
    client.chat.completions.parse.side_effect = _bad_request()
    client.chat.completions.create.return_value = _completion(
        parsed=None, content='```json\n{"summary": "from fallback"}\n```'
    )

    out, client, _ctor = _run(provider="local", base_url="http://x/v1", client=client)

    assert out.summary == "from fallback"
    kw = client.chat.completions.create.call_args.kwargs
    assert kw["response_format"] == {"type": "json_object"}
    system_text = kw["messages"][0]["content"]
    assert kw["messages"][0]["role"] == "system"
    assert "JSON" in system_text
    assert '"summary"' in system_text  # the schema is in the prompt
    assert kw["messages"][1] == {"role": "user", "content": "hi"}


def test_local_fallback_invalid_json_raises_parse_error():
    from apps.ai.providers.claude_structured import StructuredParseError

    client = MagicMock()
    client.chat.completions.parse.side_effect = _bad_request()
    client.chat.completions.create.return_value = _completion(parsed=None, content='{"nope": 1}')

    with pytest.raises(StructuredParseError):
        _run(provider="local", base_url="http://x/v1", client=client)


def test_openai_400_is_not_retried():
    client = MagicMock()
    client.chat.completions.parse.side_effect = _bad_request()

    with pytest.raises(BadRequestError):
        _run(provider="openai", client=client)
    client.chat.completions.create.assert_not_called()


def test_token_usage_from_openai_maps_cached_subset():
    from apps.ai.providers.openai_structured import token_usage_from_openai

    usage = token_usage_from_openai(_usage(prompt=1000, completion=200, cached=300))
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 200
    assert usage.cached_tokens == 300
    assert usage.cache_write_tokens == 0


def test_token_usage_from_openai_tolerates_missing_details():
    from apps.ai.providers.openai_structured import token_usage_from_openai

    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.prompt_tokens_details = None
    out = token_usage_from_openai(usage)
    assert (out.input_tokens, out.output_tokens, out.cached_tokens) == (10, 5, 0)


def test_client_gets_resilience_kwargs_and_local_placeholder_key(settings):
    settings.AI_PROVIDER_MAX_RETRIES = 4
    settings.AI_PROVIDER_TIMEOUT_SECONDS = 12.5

    _out, _client, ctor = _run(provider="local", api_key="", base_url="http://x/v1")
    kw = ctor.call_args.kwargs
    assert kw["max_retries"] == 4
    assert kw["timeout"] == 12.5
    assert kw["base_url"] == "http://x/v1"
    assert kw["api_key"]  # placeholder, never empty

    _out, _client, ctor = _run(provider="openai", api_key="sk-real")
    assert ctor.call_args.kwargs["api_key"] == "sk-real"
    assert ctor.call_args.kwargs["base_url"] is None


def test_airun_write_failure_does_not_lose_result():
    with patch("apps.ai.cost.record_ai_run", side_effect=RuntimeError("db down")):
        out, _client, _ctor = _run()
    assert out.summary == "ok"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PYTEST apps/ai/tests/test_openai_structured.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.ai.providers.openai_structured'`.

- [ ] **Step 3: Create `backend/apps/ai/providers/openai_structured.py`**

```python
"""One-shot structured run against an OpenAI-compatible chat endpoint.

Returns a parsed Pydantic model or raises. Serves both the ``openai`` provider
and ``local`` (any OpenAI-compatible server). ``chat.completions.parse`` sends
the model's JSON schema as a strict ``response_format``; a local server that
rejects strict schemas falls back once to ``json_object`` mode with the schema
in the prompt, validated client-side. The result is always schema-validated.

Separate from the streaming ``OpenAIProvider`` so the two return contracts
(typed one-shot vs event stream) stay apart. Records an ``AIRun`` under the
real provider name so cost caps see the spend (``local`` costs $0).
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import cast

from openai import BadRequestError, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ParsedChatCompletion
from pydantic import BaseModel, ValidationError

from apps.ai.providers._config import client_kwargs
from apps.ai.providers.claude_structured import StructuredParseError

logger = logging.getLogger(__name__)

# The SDK demands a key at construction; local servers ignore it (mirrors LocalProvider).
_PLACEHOLDER_KEY = "sk-local-placeholder"
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def run_structured[M: BaseModel](
    *,
    provider: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int = 2048,
    base_url: str = "",
) -> M:
    client = OpenAI(
        api_key=api_key or _PLACEHOLDER_KEY, base_url=base_url or None, **client_kwargs()
    )
    t0 = time.perf_counter()
    completion: ChatCompletion
    try:
        parsed_completion = _parse(client, provider, model, system, user, output_model, max_tokens)
        completion = parsed_completion
        parsed = _parsed_or_raise(parsed_completion, output_model)
    except BadRequestError:
        if provider != "local":
            raise
        completion, parsed = _local_fallback(
            client,
            model=model,
            system=system,
            user=user,
            output_model=output_model,
            max_tokens=max_tokens,
        )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    _record_structured_run(
        provider=provider, model=model, usage=completion.usage, latency_ms=latency_ms
    )
    return parsed


def _parse[M: BaseModel](
    client: OpenAI,
    provider: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int,
) -> ParsedChatCompletion[M]:
    """Strict-schema parse. ``max_completion_tokens`` is the current OpenAI parameter;
    older OpenAI-compatible local servers only know ``max_tokens``."""
    if provider == "local":
        return client.chat.completions.parse(
            model=model,
            messages=_messages(system, user),
            response_format=output_model,
            max_tokens=max_tokens,
        )
    return client.chat.completions.parse(
        model=model,
        messages=_messages(system, user),
        response_format=output_model,
        max_completion_tokens=max_tokens,
    )


def _messages(system: str, user: str) -> list[ChatCompletionMessageParam]:
    raw: list[dict[str, str]] = []
    if system:
        raw.append({"role": "system", "content": system})
    raw.append({"role": "user", "content": user})
    return cast(list[ChatCompletionMessageParam], raw)


def _parsed_or_raise[M: BaseModel](completion: ParsedChatCompletion[M], output_model: type[M]) -> M:
    if not completion.choices:
        raise StructuredParseError(f"No choices returned for {output_model.__name__}")
    message = completion.choices[0].message
    if message.refusal:
        raise StructuredParseError(f"Model refused {output_model.__name__}: {message.refusal}")
    if message.parsed is None:
        raise StructuredParseError(f"Model did not return a parsed {output_model.__name__} output")
    return message.parsed


def _local_fallback[M: BaseModel](
    client: OpenAI,
    *,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int,
) -> tuple[ChatCompletion, M]:
    """``json_object`` mode with the schema in the prompt, validated client-side."""
    schema = json.dumps(output_model.model_json_schema(), separators=(",", ":"))
    instruction = (
        "Respond with a single JSON object and nothing else (no prose, no code fences). "
        f"The JSON must match this JSON schema:\n{schema}"
    )
    system_text = f"{system}\n\n{instruction}" if system else instruction
    completion = client.chat.completions.create(
        model=model,
        messages=_messages(system_text, user),
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    content = completion.choices[0].message.content if completion.choices else None
    text = _FENCE.sub("", content or "").strip()
    try:
        parsed = output_model.model_validate_json(text)
    except ValidationError as exc:
        raise StructuredParseError(
            f"Local fallback returned JSON that does not match {output_model.__name__}: {exc}"
        ) from exc
    return completion, parsed


def token_usage_from_openai(usage: object):
    """Map an OpenAI usage object to TokenUsage. ``prompt_tokens`` is the total prompt;
    ``prompt_tokens_details.cached_tokens`` is the cached subset. Mirrors the streaming
    ``OpenAIProvider`` accumulation."""
    from apps.ai.types import TokenUsage

    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
    return TokenUsage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        cached_tokens=cached,
        cache_write_tokens=0,
    )


def _record_structured_run(*, provider: str, model: str, usage: object, latency_ms: int) -> None:
    """Best-effort: record this one-shot run as an AIRun so its cost counts against
    the provider caps. A ledger-write failure must never lose the already-parsed
    result, so we log and continue."""
    from apps.ai.cost import record_ai_run

    try:
        record_ai_run(
            provider=provider,
            model=model,
            usage=token_usage_from_openai(usage),
            latency_ms=latency_ms,
        )
    except Exception:  # best-effort ledger write; the parsed result is already obtained
        logger.warning(
            "run_structured: failed to record AIRun (provider=%s model=%s)",
            provider,
            model,
            exc_info=True,
        )
```

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/ai/tests/test_openai_structured.py apps/ai/tests/test_structured_records_airun.py`
Expected: PASS (14 new + existing Claude tests).

- [ ] **Step 5: Lint the new module**

Run: `$RUN -w /app web uv run ruff check backend/apps/ai/providers/openai_structured.py backend/apps/ai/tests/test_openai_structured.py && $RUN -w /app web uv run ruff format --check backend/apps/ai/providers/openai_structured.py backend/apps/ai/tests/test_openai_structured.py && $RUN -w /app web uv run mypy backend/apps/ai/providers/openai_structured.py`
Expected: clean. (`ruff format` may want the long `_parsed_or_raise` signature wrapped; apply `ruff format` to the two files and re-check.)

- [ ] **Step 6: Commit**

```bash
cd $WT && git add backend/apps/ai/providers/openai_structured.py backend/apps/ai/tests/test_openai_structured.py
LEFTHOOK=0 git commit -m "feat(ai): one-shot structured output for OpenAI-compatible providers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Facade with target resolution + strict-schema conformance test

**Files:**
- Create: `backend/apps/ai/structured.py`
- Test: `backend/apps/ai/tests/test_structured_facade.py` (new), `backend/apps/ai/tests/test_structured_schemas_strict.py` (new)

**Interfaces:**
- Consumes: Task 1 `default_model_for`, `CLAUDE_FAMILY_PROVIDERS`; Task 2 `openai_structured.run_structured`, `token_usage_from_openai`; existing `claude_structured.run_structured`, `StructuredParseError`, `token_usage_from_anthropic`; `apps.ai.router._calibration_choice() -> tuple[str, str] | None`; `apps.ai.cost.check_daily_cap(provider, cap_usd=)`, `check_monthly_cap(provider, cap_usd=)`, `CostCapExceededError`.
- Produces (used by Tasks 4–8):
  - `run_structured(*, provider, api_key, model, system, user, output_model, max_tokens=2048, base_url="") -> M`
  - `class StructuredTarget(NamedTuple): provider: str; model: str; api_key: str; base_url: str; daily_cap: Decimal; monthly_cap: Decimal | None`
  - `resolve_structured_target(*, profile=None, override_provider="", override_model="") -> StructuredTarget | None`
  - `structured_capable_targets() -> list[StructuredTarget]`
  - `ensure_within_caps(target: StructuredTarget) -> None`
  - re-exports `StructuredParseError`, `token_usage_from_anthropic`, `token_usage_from_openai`

- [ ] **Step 1: Write the failing facade tests**

Create `backend/apps/ai/tests/test_structured_facade.py`:

```python
"""``apps.ai.structured`` — the provider-neutral entry point for one-shot
structured output and the target resolution the callers share."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from cryptography.fernet import InvalidToken
from pydantic import BaseModel

from apps.ai.cost import CostCapExceededError
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig

pytestmark = pytest.mark.django_db


class _Out(BaseModel):
    summary: str


def _kw(**overrides):
    kw = dict(api_key="k", model="m", system="s", user="u", output_model=_Out, base_url="")
    kw.update(overrides)
    return kw


# --- dispatch ---------------------------------------------------------------


@pytest.mark.parametrize("provider", ["claude", "anthropic"])
def test_claude_family_dispatches_to_anthropic_impl(provider):
    from apps.ai import structured

    with (
        patch.object(structured.claude_structured, "run_structured", return_value=_Out(summary="c")) as c,
        patch.object(structured.openai_structured, "run_structured") as o,
    ):
        out = structured.run_structured(provider=provider, **_kw())
    assert out.summary == "c"
    o.assert_not_called()
    assert "provider" not in c.call_args.kwargs
    assert c.call_args.kwargs["model"] == "m"


@pytest.mark.parametrize("provider", ["openai", "local"])
def test_openai_compatible_dispatches_with_provider(provider):
    from apps.ai import structured

    with (
        patch.object(structured.claude_structured, "run_structured") as c,
        patch.object(structured.openai_structured, "run_structured", return_value=_Out(summary="o")) as o,
    ):
        out = structured.run_structured(provider=provider, **_kw(base_url="http://x/v1"))
    assert out.summary == "o"
    c.assert_not_called()
    assert o.call_args.kwargs["provider"] == provider
    assert o.call_args.kwargs["base_url"] == "http://x/v1"


def test_unknown_provider_raises():
    from apps.ai.structured import run_structured

    with pytest.raises(ValueError, match="Unknown provider"):
        run_structured(provider="bard", **_kw())


def test_reexports():
    from apps.ai import structured
    from apps.ai.providers.claude_structured import StructuredParseError

    assert structured.StructuredParseError is StructuredParseError
    assert callable(structured.token_usage_from_anthropic)
    assert callable(structured.token_usage_from_openai)


# --- resolution -------------------------------------------------------------


def _cfg(provider, *, key="", model="", base_url="", enabled=True):
    cfg = ProviderConfig.objects.create(
        provider=provider, default_model=model, base_url=base_url, enabled=enabled
    )
    if key:
        cfg.api_key = key
        cfg.save()
    return cfg


def test_override_provider_wins_and_uses_override_model():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai", model="gpt-5")
    t = resolve_structured_target(override_provider="openai", override_model="gpt-6-astra")
    assert t is not None
    assert (t.provider, t.model, t.api_key) == ("openai", "gpt-6-astra", "sk-oai")


def test_override_without_model_falls_back_to_config_then_catalog_default():
    from apps.ai.structured import resolve_structured_target

    _cfg("openai", key="sk-oai", model="gpt-5")
    assert resolve_structured_target(override_provider="openai").model == "gpt-5"

    ProviderConfig.objects.all().delete()
    _cfg("openai", key="sk-oai")
    assert resolve_structured_target(override_provider="openai").model == "gpt-5.6-sol"


def test_profile_defaults_used_when_no_override():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai", model="gpt-5")
    profile = TradingProfile.objects.create(
        name="p", style="s", default_provider="openai", default_model="gpt-5.6-sol"
    )
    t = resolve_structured_target(profile=profile)
    assert (t.provider, t.model) == ("openai", "gpt-5.6-sol")


def test_profile_provider_without_usable_config_yields_none_no_fallthrough():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    profile = TradingProfile.objects.create(name="p", style="s", default_provider="openai")
    assert resolve_structured_target(profile=profile) is None


def test_calibration_choice_used_when_enabled(settings):
    from apps.ai.structured import resolve_structured_target

    settings.AI_CALIBRATION_ROUTING_ENABLED = True
    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai", model="gpt-5.6-sol")
    with patch("apps.ai.router._calibration_choice", return_value=("openai", "gpt-5.6-sol")):
        t = resolve_structured_target()
    assert (t.provider, t.model) == ("openai", "gpt-5.6-sol")


def test_first_enabled_config_is_the_last_resort():
    from apps.ai.structured import resolve_structured_target

    _cfg("openai", key="sk-oai", model="gpt-5")
    _cfg("claude", key="sk-ant", model="claude-opus-5")
    t = resolve_structured_target()
    assert t.provider == "openai"  # lowest id


def test_disabled_and_keyless_configs_are_unusable():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="m", enabled=False)
    _cfg("openai", model="gpt-5")  # enabled, no key
    assert resolve_structured_target() is None
    assert resolve_structured_target(override_provider="claude") is None
    assert resolve_structured_target(override_provider="openai") is None


def test_local_usable_with_base_url_and_no_key_but_needs_a_model():
    from apps.ai.structured import resolve_structured_target

    _cfg("local", base_url="http://host.docker.internal:11434/v1")
    assert resolve_structured_target(override_provider="local") is None  # no model anywhere

    ProviderConfig.objects.all().delete()
    _cfg("local", base_url="http://host.docker.internal:11434/v1", model="llama3")
    t = resolve_structured_target(override_provider="local")
    assert (t.provider, t.model, t.api_key) == ("local", "llama3", "")

    ProviderConfig.objects.all().delete()
    _cfg("local", model="llama3")  # no base_url
    assert resolve_structured_target(override_provider="local") is None


def test_target_carries_caps():
    from apps.ai.structured import resolve_structured_target

    cfg = _cfg("claude", key="sk-ant", model="m")
    cfg.daily_cost_cap_usd = Decimal("3.00")
    cfg.monthly_cost_cap_usd = Decimal("40.00")
    cfg.save()
    t = resolve_structured_target()
    assert (t.daily_cap, t.monthly_cap) == (Decimal("3.00"), Decimal("40.00"))


def _corrupt_key(provider: str) -> None:
    from django.db import connection

    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet", provider],
        )


def test_single_target_lets_invalid_token_propagate():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="m")
    _corrupt_key("claude")
    with pytest.raises(InvalidToken):
        resolve_structured_target(override_provider="claude")


def test_capable_targets_enumerates_every_usable_provider_and_skips_undecryptable():
    from apps.ai.structured import structured_capable_targets

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai")  # model from catalog default
    _cfg("local", base_url="http://x/v1", model="llama3")
    _corrupt_key("claude")

    targets = structured_capable_targets()
    assert [(t.provider, t.model) for t in targets] == [
        ("local", "llama3"),
        ("openai", "gpt-5.6-sol"),
    ]


def test_ensure_within_caps_delegates_to_cost_checks():
    from apps.ai.structured import StructuredTarget, ensure_within_caps

    t = StructuredTarget("openai", "m", "k", "", Decimal("1.00"), None)
    with (
        patch("apps.ai.cost.check_daily_cap") as d,
        patch("apps.ai.cost.check_monthly_cap") as m,
    ):
        ensure_within_caps(t)
    d.assert_called_once_with("openai", cap_usd=Decimal("1.00"))
    m.assert_called_once_with("openai", cap_usd=None)

    with (
        patch("apps.ai.cost.check_daily_cap", side_effect=CostCapExceededError("over")),
        pytest.raises(CostCapExceededError),
    ):
        ensure_within_caps(t)
```

Create `backend/apps/ai/tests/test_structured_schemas_strict.py`:

```python
"""Every output model handed to ``run_structured`` must survive OpenAI's strict
JSON-schema conversion: all properties required, ``additionalProperties`` off,
no Pydantic feature strict mode rejects. Offline guard for the OpenAI path."""

from __future__ import annotations

import pytest
from openai.lib._pydantic import to_strict_json_schema

from apps.book.services.narrative import BookNarrative
from apps.observer.schemas import ObservationReport
from apps.strategy.coverage.schemas import CoverageRevisionDraft
from apps.strategy.regime.services.narrative import RegimeNarrative
from apps.strategy.warroom.services.verdict import WarRoomVerdict
from apps.thesis.schemas import PostMortemReport


@pytest.mark.parametrize(
    "model",
    [
        ObservationReport,
        PostMortemReport,
        CoverageRevisionDraft,
        RegimeNarrative,
        BookNarrative,
        WarRoomVerdict,
    ],
)
def test_output_model_converts_to_strict_schema(model):
    schema = to_strict_json_schema(model)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$PYTEST apps/ai/tests/test_structured_facade.py apps/ai/tests/test_structured_schemas_strict.py`
Expected: the facade file fails with `ModuleNotFoundError: No module named 'apps.ai.structured'`. The strict-schema file should PASS already (it tests existing models against the SDK); if any model fails, note which and fix it in Step 3b below.

- [ ] **Step 3: Create `backend/apps/ai/structured.py`**

```python
"""Provider-neutral one-shot structured output.

The public entry point for every caller that needs a typed Pydantic result in
one call (observer structured mode and consensus, the eval harness, post-mortems,
coverage revisions, regime/book narratives, the War Room verdict). Dispatches
to the Anthropic ``messages.parse`` implementation for Claude-family providers
and to the OpenAI-compatible implementation for ``openai`` and ``local``. Both
record an ``AIRun`` under the real provider so cost caps see the spend.

Target resolution mirrors ``apps.ai.router``: explicit override, then the
profile's defaults, then calibration-weighted routing (opt-in), then the first
enabled ``ProviderConfig``. A target is usable when its config is enabled and
carries a credential — a key for ``claude``/``openai``, a base URL for ``local``.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import NamedTuple

from cryptography.fernet import InvalidToken
from django.conf import settings
from pydantic import BaseModel

from apps.ai.catalog import CLAUDE_FAMILY_PROVIDERS, default_model_for
from apps.ai.providers import claude_structured, openai_structured
from apps.ai.providers.claude_structured import StructuredParseError, token_usage_from_anthropic
from apps.ai.providers.openai_structured import token_usage_from_openai

log = logging.getLogger(__name__)

OPENAI_COMPATIBLE_PROVIDERS = ("openai", "local")

__all__ = [
    "OPENAI_COMPATIBLE_PROVIDERS",
    "StructuredParseError",
    "StructuredTarget",
    "ensure_within_caps",
    "resolve_structured_target",
    "run_structured",
    "structured_capable_targets",
    "token_usage_from_anthropic",
    "token_usage_from_openai",
]


def run_structured[M: BaseModel](
    *,
    provider: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int = 2048,
    base_url: str = "",
) -> M:
    """Run ``output_model`` as a one-shot structured call on ``provider``."""
    if provider in CLAUDE_FAMILY_PROVIDERS:
        return claude_structured.run_structured(
            api_key=api_key,
            model=model,
            system=system,
            user=user,
            output_model=output_model,
            max_tokens=max_tokens,
            base_url=base_url,
        )
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return openai_structured.run_structured(
            provider=provider,
            api_key=api_key,
            model=model,
            system=system,
            user=user,
            output_model=output_model,
            max_tokens=max_tokens,
            base_url=base_url,
        )
    raise ValueError(f"Unknown provider for structured output: {provider!r}")


class StructuredTarget(NamedTuple):
    """A usable (provider, model) plus the credential and caps a caller needs.

    Named fields keep the secret ``api_key`` distinct from the loggable
    ``provider``/``model`` for data-flow analysis; it still unpacks like a tuple.
    """

    provider: str
    model: str
    api_key: str
    base_url: str
    daily_cap: Decimal
    monthly_cap: Decimal | None


def _target_from_config(cfg, *, model: str = "") -> StructuredTarget | None:
    """Build a target from ``cfg`` or return None when it is missing, disabled, or
    lacks a credential/model. Reads the encrypted key, so ``InvalidToken`` can raise."""
    if cfg is None or not cfg.enabled:
        return None
    key = cfg.api_key
    base_url = cfg.base_url or ""
    if cfg.provider == "local":
        if not base_url:
            return None
    elif not key:
        return None
    model_id = model or cfg.default_model or default_model_for(cfg.provider)
    if not model_id:
        return None
    return StructuredTarget(
        provider=cfg.provider,
        model=model_id,
        api_key=key,
        base_url=base_url,
        daily_cap=cfg.daily_cost_cap_usd,
        monthly_cap=cfg.monthly_cost_cap_usd,
    )


def resolve_structured_target(
    *, profile=None, override_provider: str = "", override_model: str = ""
) -> StructuredTarget | None:
    """The target a structured caller should use, or None when nothing usable exists.

    Precedence: ``override_provider`` → ``profile.default_provider`` →
    calibration-weighted choice (``AI_CALIBRATION_ROUTING_ENABLED``) → first enabled
    config. An override or profile that names a provider does not fall through to
    the global tiers when that provider is unusable. ``InvalidToken`` propagates so
    callers can report an undecryptable key.
    """
    from apps.secrets.models import ProviderConfig

    if override_provider:
        cfg = ProviderConfig.objects.filter(provider=override_provider, enabled=True).first()
        return _target_from_config(cfg, model=override_model)
    if profile is not None and getattr(profile, "default_provider", ""):
        cfg = ProviderConfig.objects.filter(
            provider=profile.default_provider, enabled=True
        ).first()
        return _target_from_config(cfg, model=getattr(profile, "default_model", "") or "")
    if getattr(settings, "AI_CALIBRATION_ROUTING_ENABLED", False):
        from apps.ai.router import _calibration_choice

        choice = _calibration_choice()
        if choice is not None:
            prov, model_id = choice
            cfg = ProviderConfig.objects.filter(provider=prov, enabled=True).first()
            target = _target_from_config(cfg, model=model_id)
            if target is not None:
                return target
    cfg = ProviderConfig.objects.filter(enabled=True).order_by("id").first()
    return _target_from_config(cfg)


def structured_capable_targets() -> list[StructuredTarget]:
    """Every enabled provider with a usable credential and a resolvable model, one
    per config, ordered by provider name. Undecryptable keys are skipped with a
    warning so a consensus fan-out never crashes on a key/salt rotation."""
    from apps.secrets.models import ProviderConfig

    targets: list[StructuredTarget] = []
    for cfg in ProviderConfig.objects.filter(enabled=True).order_by("provider"):
        try:
            target = _target_from_config(cfg)
        except InvalidToken:
            log.warning("structured: %s API key could not be decrypted; skipping", cfg.provider)
            continue
        if target is not None:
            targets.append(target)
    return targets


def ensure_within_caps(target: StructuredTarget) -> None:
    """Raise ``CostCapExceededError`` when ``target.provider`` is over its daily or
    monthly cap. Reads AIRun spend only; never calls the model."""
    from apps.ai.cost import check_daily_cap, check_monthly_cap

    check_daily_cap(target.provider, cap_usd=target.daily_cap)
    check_monthly_cap(target.provider, cap_usd=target.monthly_cap)
```

- [ ] **Step 3b (only if Step 2 showed a strict-schema failure):** the failing model uses a Pydantic feature strict mode rejects. Make the field strict-compatible in that model (optional fields become `X | None` with an explicit `default=None`; free-form `dict` fields become a typed model) and re-run. Record what changed in the commit message.

- [ ] **Step 4: Run the tests**

Run: `$PYTEST apps/ai/tests/test_structured_facade.py apps/ai/tests/test_structured_schemas_strict.py apps/ai/tests/test_router.py`
Expected: PASS.

- [ ] **Step 5: Lint and type-check**

Run: `$RUN -w /app web uv run ruff check backend/apps/ai && $RUN -w /app web uv run ruff format --check backend/apps/ai && $RUN -w /app web uv run mypy backend/apps/ai`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd $WT && git add backend/apps/ai/structured.py backend/apps/ai/tests/test_structured_facade.py backend/apps/ai/tests/test_structured_schemas_strict.py
LEFTHOOK=0 git commit -m "feat(ai): provider-neutral structured facade with shared target resolution

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Observer structured mode on any provider (run.py, serializer, batch import)

**Files:**
- Modify: `backend/apps/observer/services/run.py:13-15` (imports), `:274-300` (guard), `:333-343` (call)
- Modify: `backend/apps/observer/serializers.py:88-112`
- Modify: `backend/apps/observer/services/batch.py:25`
- Test: `backend/apps/observer/tests/test_structured_outputs.py:113-137`, `backend/apps/observer/tests/test_schedules_endpoint.py:122-135`

**Interfaces:**
- Consumes: Task 3 `apps.ai.structured.run_structured`, `token_usage_from_anthropic`; Task 1 `default_model_for`.

- [ ] **Step 1: Rewrite the two tests that pin the old behaviour**

In `backend/apps/observer/tests/test_structured_outputs.py` replace `test_structured_non_claude_provider_skips_with_visible_message` (lines 113–137) with:

```python
def test_structured_openai_provider_runs_and_records_its_provider(
    db,
    schedule_structured,
    fake_report,
) -> None:
    """Structured output has provider parity: an openai schedule runs the same
    ObservationReport call through the facade and the resulting prediction is
    attributed to openai."""
    from apps.observer.services import run as run_service
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    cfg = ProviderConfig.objects.create(provider="openai", enabled=True)
    cfg.api_key = "sk-oai"
    cfg.save()
    thread = get_or_create_observer_thread(schedule_structured.profile)
    with patch.object(run_service, "run_structured", return_value=fake_report) as run_structured:
        run_service._run_structured_and_record(
            schedule_structured, thread, "payload", "openai", cfg, snap=None
        )

    kw = run_structured.call_args.kwargs
    assert kw["provider"] == "openai"
    assert kw["model"] == "gpt-5.6-sol"  # catalog default for an openai config with no model
    assert kw["api_key"] == "sk-oai"
    msg = Message.objects.filter(thread=thread, role="assistant", status="done").first()
    assert msg is not None
    assert msg.content["kind"] == "structured_observation"
    assert not Message.objects.filter(thread=thread, error="unsupported_provider").exists()
```

In `backend/apps/observer/tests/test_schedules_endpoint.py` replace `test_create_structured_schedule_requires_claude_provider` (lines 122–135) with:

```python
@pytest.mark.django_db
def test_create_structured_schedule_accepts_any_provider(api):
    """structured output has provider parity, so an openai-resolving schedule is
    accepted; only use_batch stays Claude-only."""
    p = TradingProfile.objects.create(name="O", style="x", default_provider="openai")
    resp = api.post(
        "/api/observer/schedules/",
        {"name": "s", "profile": p.id, "cron": "0 * * * *", "structured": True},
        format="json",
    )
    assert resp.status_code == 201, resp.content
```

- [ ] **Step 2: Run them to verify they fail**

Run: `$PYTEST apps/observer/tests/test_structured_outputs.py apps/observer/tests/test_schedules_endpoint.py`
Expected: the two rewritten tests FAIL (guard still records `unsupported_provider`; endpoint returns 400).

- [ ] **Step 3: Edit `backend/apps/observer/services/run.py`**

Imports (lines 13–15):

```python
from apps.ai.catalog import default_model_for
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.structured import run_structured
```

(`CLAUDE_FAMILY_PROVIDERS` and `DEFAULT_CLAUDE_MODEL` have no other use in this file; ruff F401 confirms.)

In `_run_structured_and_record`, delete the whole `if provider_name not in CLAUDE_FAMILY_PROVIDERS:` block (the guard plus its `Message.objects.create(...)` and `return`), and change the docstring to `"""Run the structured ObservationReport call on the schedule's provider and persist the result."""`. Then change the model resolution and the call:

```python
    model_id = sched.override_model or cfg.default_model or default_model_for(provider_name)
    try:
        report = run_structured(
            provider=provider_name,
            api_key=cfg.api_key,
            model=model_id,
            system=build_system_prompt(sched.profile, now=timezone.now()),
            user=payload_text,
            output_model=ObservationReport,
            base_url=cfg.base_url or "",
        )
```

- [ ] **Step 4: Edit `backend/apps/observer/serializers.py:88-112`**

Replace `_validate_claude_only_modes` with:

```python
    def _validate_claude_only_modes(self, attrs) -> None:
        """``use_batch`` runs through Anthropic Messages Batches; reject it at
        configuration time rather than letting every fire 401 against
        api.anthropic.com with a non-Claude key. ``structured`` has provider parity
        (``apps.ai.structured``) and is not gated."""
        from apps.ai.catalog import CLAUDE_FAMILY_PROVIDERS

        if not self._resolved(attrs, "use_batch", default=False):
            return
        profile = self._resolved(attrs, "profile", default=None)
        provider = self._resolved(attrs, "override_provider", default="") or getattr(
            profile, "default_provider", ""
        )
        if provider not in CLAUDE_FAMILY_PROVIDERS:
            raise serializers.ValidationError(
                {
                    "use_batch": (
                        "use_batch requires a Claude provider; this schedule "
                        f"resolves to {provider!r}"
                    )
                }
            )
```

- [ ] **Step 5: Edit `backend/apps/observer/services/batch.py:25`**

```python
from apps.ai.structured import token_usage_from_anthropic
```

- [ ] **Step 6: Run the observer suite plus the two cross-app tests that patch the observer's `run_structured` name**

Run: `$PYTEST apps/observer apps/threads/tests/test_coach_injection.py`
Expected: PASS. `test_patch_use_batch_on_non_claude_schedule_rejected` and `test_create_batch_schedule_requires_claude_provider` still pass (batch gate kept).

- [ ] **Step 7: Commit**

```bash
cd $WT && git add backend/apps/observer/services/run.py backend/apps/observer/serializers.py backend/apps/observer/services/batch.py backend/apps/observer/tests/test_structured_outputs.py backend/apps/observer/tests/test_schedules_endpoint.py
LEFTHOOK=0 git commit -m "feat(observer): structured mode runs on any configured provider

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Cross-vendor consensus

**Files:**
- Modify: `backend/apps/observer/services/consensus.py` (module docstring, imports, `StructuredPair`, `structured_capable_pairs`, the `run_structured` call)
- Test: `backend/apps/observer/tests/test_consensus_service.py:269-289`

**Interfaces:**
- Consumes: Task 3 `StructuredTarget`, `structured_capable_targets`, `run_structured`.
- Produces: `structured_capable_pairs() -> list[StructuredTarget]` and `StructuredPair = StructuredTarget` (names kept for the existing tests and any patch site).

- [ ] **Step 1: Rewrite the selection test**

Replace `test_structured_capable_pairs_selects_claude_family_only` (lines 269–289) with:

```python
def test_structured_capable_pairs_selects_every_usable_provider():
    """Every enabled config with a credential + model is structured-capable:
    a key for claude/openai, a base_url for local."""
    claude = ProviderConfig.objects.create(provider="claude", default_model="claude-opus-4-8")
    claude.api_key = "sk-ant-1"  # type: ignore[misc]
    claude.save()
    openai = ProviderConfig.objects.create(provider="openai", default_model="gpt-5")
    openai.api_key = "sk-oai"  # type: ignore[misc]
    openai.save()
    ProviderConfig.objects.create(
        provider="local", default_model="llama", base_url="http://host.docker.internal:11434/v1"
    )

    from apps.observer.services.consensus import structured_capable_pairs

    pairs = structured_capable_pairs()
    assert [(p[0], p[1]) for p in pairs] == [
        ("claude", "claude-opus-4-8"),
        ("local", "llama"),
        ("openai", "gpt-5"),
    ]
    assert pairs[0][2] == "sk-ant-1"
    assert pairs[1][2] == ""  # local: no key needed
    assert pairs[2][2] == "sk-oai"


def test_structured_capable_pairs_skips_local_without_base_url():
    ProviderConfig.objects.create(provider="local", default_model="llama")
    from apps.observer.services.consensus import structured_capable_pairs

    assert structured_capable_pairs() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `$PYTEST apps/observer/tests/test_consensus_service.py`
Expected: the two tests FAIL (openai/local excluded today).

- [ ] **Step 3: Edit `backend/apps/observer/services/consensus.py`**

Module docstring becomes:

```python
"""Cross-model consensus signal.

Fans the same structured ObservationReport prompt across every usable enabled
provider (claude / openai / local — see ``apps.ai.structured``) and measures
agreement. Agreement is a confidence signal a single model can't give;
divergence flags "do more homework". With fewer than 2 usable providers the
result is an explicit single-provider/no-consensus shape — never a fabricated
consensus.

OPT-IN ONLY: this multiplies cost ~Nx, so it is gated behind the schedule's
``consensus`` flag and respects each provider's daily/monthly cost cap.
"""
```

Imports: drop `NamedTuple`, `Decimal`, `InvalidToken`, `DEFAULT_CLAUDE_MODEL`, `ProviderConfig`, and the `claude_structured` import; add:

```python
from apps.ai.structured import StructuredTarget, run_structured, structured_capable_targets
```

Delete `_STRUCTURED_PROVIDERS`, the `StructuredPair` class, and the body of `structured_capable_pairs`; replace with:

```python
# The consensus loop's name for a usable (provider, model, key, base_url, caps) target.
StructuredPair = StructuredTarget


def structured_capable_pairs() -> list[StructuredTarget]:
    """Every usable enabled provider, one per config (``apps.ai.structured``)."""
    return structured_capable_targets()
```

In `consensus_report`, the call becomes:

```python
            report: ObservationReport = run_structured(
                provider=pair.provider,
                api_key=pair.api_key,
                model=pair.model,
                system=system,
                user=user,
                output_model=ObservationReport,
                base_url=pair.base_url,
            )
```

Keep `_DEGRADED_NOTE`, `_modal_and_agreement`, the cap checks, and the aggregation unchanged. Update the `consensus_report` docstring's first line to "Run ObservationReport across every usable provider, aggregate agreement."

- [ ] **Step 4: Run the consensus suites**

Run: `$PYTEST apps/observer/tests/test_consensus_service.py apps/observer/tests/test_consensus_observer.py apps/observer/tests/test_task_acks.py`
Expected: PASS. Tests that construct `StructuredPair(...)` positionally keep working (same field order).

- [ ] **Step 5: Commit**

```bash
cd $WT && git add backend/apps/observer/services/consensus.py backend/apps/observer/tests/test_consensus_service.py
LEFTHOOK=0 git commit -m "feat(observer): consensus fans out across every usable provider

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Eval harness on any provider

**Files:**
- Modify: `backend/apps/analytics/services/aieval.py:1-33` (docstring/import), `:149-195` (`replay_one`), `:199-215` (`evaluate` signature + call), `:291-313` (`preflight_cost_cap` docstring only)
- Modify: `backend/apps/analytics/management/commands/aieval.py:35-55`, `:66-80`
- Modify: `backend/apps/analytics/tasks.py` if it calls `evaluate(...)` (grep `evaluate(` in `backend/apps/analytics/`) — pass `provider="claude"` explicitly there.
- Test: `backend/apps/analytics/tests/test_aieval.py` (append)

**Interfaces:**
- Consumes: Task 3 `run_structured`; Task 1 `default_model_for` is not needed (the model is always explicit here).
- Produces: `replay_one(example, *, system, model, provider="claude")`, `evaluate(*, system, model, label, horizon=None, limit=None, provider="claude")`, command flag `--provider`.

- [ ] **Step 1: Write the failing tests** (append to `test_aieval.py`; reuse the file's existing `profile` fixture and the `_record_spend` helper)

```python
def test_replay_one_on_openai_resolves_openai_config_and_passes_provider(profile):
    """The eval harness can score any provider: cfg lookup + serialize_for_ai +
    run_structured all key off the requested provider."""
    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.create(provider="openai", enabled=True)
    cfg.api_key = "sk-oai"
    cfg.save()
    snap = _snapshot(profile)
    pm = _postmortem(
        _thesis(profile, direction="bullish", snapshot=snap), verdict="correct", fwd=5.0
    )
    with patch.object(svc, "run_structured", return_value=_report("bullish")) as rs:
        out = replay_one(pm, system="sys", model="gpt-5.6-sol", provider="openai")

    kw = rs.call_args.kwargs
    assert kw["provider"] == "openai"
    assert kw["api_key"] == "sk-oai"
    assert kw["model"] == "gpt-5.6-sol"
    assert out["predicted_direction"] == "bullish"
    assert out["hit"] is True


def test_command_provider_flag_preflights_that_provider(profile):
    """--provider openai checks openai's caps, not claude's."""
    from decimal import Decimal

    from django.core.management.base import CommandError

    from apps.secrets.models import ProviderConfig

    _record_spend(provider="openai", cost="2.00")
    ProviderConfig.objects.create(provider="openai", daily_cost_cap_usd=Decimal("1.00"))
    with pytest.raises(CommandError, match="cap"):
        call_command("aieval", "--model", "gpt-5.6-sol", "--provider", "openai")


def test_evaluate_threads_provider_to_replay(profile):
    row = {
        "predicted_direction": None,
        "confidence": None,
        "actual_verdict": "correct",
        "thesis_direction": "bullish",
        "outcome_direction": "bullish",
        "hit": None,
    }
    with (
        patch.object(svc, "replay_one", return_value=row) as replay,
        patch.object(svc, "labeled_examples", return_value=[object()]),
    ):
        res = evaluate(system="s", model="gpt-5.6-sol", label="x", provider="openai")
    assert replay.call_args.kwargs["provider"] == "openai"
    assert res["provider"] == "openai"
```

`_snapshot`, `_thesis`, `_postmortem`, `_report`, `_record_spend`, `svc`, `replay_one`, `evaluate`, `call_command`, `patch`, and `pytest` are already defined or imported at the top of `test_aieval.py`; the three local imports above are the only additions.

- [ ] **Step 2: Run to verify failure**

Run: `$PYTEST apps/analytics/tests/test_aieval.py -k "openai or provider_flag or threads_provider"`
Expected: FAIL — `TypeError: replay_one() got an unexpected keyword argument 'provider'` / `--provider` unrecognized.

- [ ] **Step 3: Edit `backend/apps/analytics/services/aieval.py`**

Import: `from apps.ai.structured import run_structured` (replace the `claude_structured` import). In the module docstring, change "the user turn handed to ``run_structured``" sentence to end "…must contain only the snapshot, whichever provider scores it."

`replay_one`:

```python
def replay_one(
    example: PostMortem, *, system: str, model: str, provider: str = "claude"
) -> dict[str, Any]:
    """Re-serialize the frozen snapshot, run the candidate on ``provider``, extract the call.

    Look-ahead-safe: the user turn is the BARE serialized snapshot — no coach,
    no recall, no post-trade context (see module docstring). Returns
    ``{predicted_direction, confidence, actual_verdict, thesis_direction,
    outcome_direction, hit}``. ``hit`` is None when the model gave no directional
    call (e.g. 'mixed'), so it is excluded from hit-rate/Brier upstream.
    """
    from apps.secrets.models import ProviderConfig

    thesis = example.thesis
    snapshot = thesis.snapshot
    if snapshot is None:  # callers filter thesis__snapshot__isnull=False; defensive
        raise ValueError(f"PostMortem {example.id}: thesis has no snapshot to replay")

    # ONLY the frozen snapshot — deliberately no coach/recall context.
    payload_text = serialize_for_ai(snapshot, provider=provider, model=model)

    try:
        cfg = ProviderConfig.objects.filter(provider=provider).first()
    except InvalidToken:
        cfg = None  # undecryptable key → empty key; run_structured fails cleanly downstream
    api_key = cfg.api_key if cfg else ""
    base_url = (cfg.base_url if cfg else "") or ""

    report = run_structured(
        provider=provider,
        api_key=api_key,
        model=model,
        system=system,
        user=payload_text,
        output_model=ObservationReport,
        base_url=base_url,
    )
    # ... rest unchanged
```

`evaluate`: add `provider: str = "claude"` after `limit`, and call `replay_one(ex, system=system, model=model, provider=provider)`. Add `"provider": provider` to the returned dict.

`preflight_cost_cap`: no code change; first docstring line becomes "Raise CostCapExceededError if ``provider``'s configured caps are already breached, BEFORE spending on a real eval run."

- [ ] **Step 4: Edit the management command**

Add after the `--model` argument:

```python
        parser.add_argument(
            "--provider",
            default="claude",
            choices=["claude", "openai", "local"],
            help="Provider that serves --model (default: claude).",
        )
```

Change `preflight_cost_cap("claude")` to `preflight_cost_cap(options["provider"])` and pass `provider=options["provider"]` into `evaluate(...)`. In the success line, print `provider={res['provider']}` before `model=`.

Then run `grep -rn "evaluate(" backend/apps/analytics --include=*.py | grep -v tests` and, for the scheduled task in `backend/apps/analytics/tasks.py`, pass `provider="claude"` explicitly (it keeps scoring the Claude default; scheduled multi-provider eval is out of scope).

- [ ] **Step 5: Run the analytics suite**

Run: `$PYTEST apps/analytics`
Expected: PASS, including the persisted-EvalRun tests (the result dict's extra `provider` key is ignored by `persist_eval_run`, which reads fields with `.get`).

- [ ] **Step 6: Commit**

```bash
cd $WT && git add backend/apps/analytics
LEFTHOOK=0 git commit -m "feat(analytics): eval harness scores any provider (--provider)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: War Room synthesizer on the resolved provider

**Files:**
- Modify: `backend/apps/strategy/warroom/services/convene.py:8-33` (`_claude_cfg` → `_synth_target`)
- Modify: `backend/apps/strategy/warroom/services/verdict.py:7`, `:27-37`
- Modify: `backend/apps/strategy/tasks.py:25`, `:94-102`
- Test: `backend/apps/strategy/warroom/tests/test_verdict.py`, `backend/apps/strategy/warroom/tests/test_convene.py:33-36`, `:49-58`

**Interfaces:**
- Consumes: Task 3 `resolve_structured_target`, `ensure_within_caps`, `StructuredTarget`, `run_structured`.
- Produces: `convene._synth_target() -> StructuredTarget | None`; `verdict.synthesize(subject_context, persona_args, *, provider, api_key, model, base_url) -> WarRoomVerdict`.

- [ ] **Step 1: Update the tests first**

`test_verdict.py` — pass `provider="openai"` and assert it reaches `run_structured`:

```python
    out = V.synthesize(
        "ctx",
        [{"persona": "bull", "argument": "a"}],
        provider="openai",
        api_key="k",
        model="m",
        base_url="",
    )
    assert out.confidence == 0.62
    assert "bull" in cap["user"].lower()
    assert cap["provider"] == "openai"
```

`test_convene.py` — in `_patch`, replace the `_claude_cfg` line with:

```python
    from apps.ai.structured import StructuredTarget

    monkeypatch.setattr(
        T,
        "_synth_target",
        lambda: StructuredTarget("openai", "gpt-5.6-sol", "k", "", Decimal("10.00"), None),
    )
```

(add `from decimal import Decimal` at the top), and in `test_convene_no_provider_errors` replace `monkeypatch.setattr(T, "_claude_cfg", lambda: None)` with `monkeypatch.setattr(T, "_synth_target", lambda: None)`. Add one test:

```python
def test_synth_target_resolves_first_enabled_provider_and_checks_caps(monkeypatch):
    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.create(provider="openai", enabled=True)
    cfg.api_key = "sk-oai"
    cfg.save()
    t = CV._synth_target()
    assert t is not None
    assert (t.provider, t.model) == ("openai", "gpt-5.6-sol")

    from apps.ai.cost import CostCapExceededError

    def _over(target):
        raise CostCapExceededError("over")

    monkeypatch.setattr(CV, "ensure_within_caps", _over)
    assert CV._synth_target() is None
```

- [ ] **Step 2: Run to verify failure**

Run: `$PYTEST apps/strategy/warroom/tests/test_verdict.py apps/strategy/warroom/tests/test_convene.py`
Expected: FAIL (`_synth_target` missing; `synthesize()` rejects `provider`).

- [ ] **Step 3: Edit `convene.py`**

Replace the `DEFAULT_CLAUDE_MODEL` import and `_claude_cfg` with:

```python
from apps.ai.structured import StructuredTarget, ensure_within_caps, resolve_structured_target
```

```python
def _synth_target() -> StructuredTarget | None:
    """The provider that synthesizes the verdict: the app's default resolution
    (calibration choice when enabled, else first enabled config), cap-checked.
    None when nothing usable exists or the provider is over its cap."""
    from apps.ai.cost import CostCapExceededError

    try:
        target = resolve_structured_target()
        if target is None:
            return None
        ensure_within_caps(target)
        return target
    except CostCapExceededError as exc:
        log.warning("warroom.cap_hit: %s", exc)
        return None
    except Exception:
        log.warning("warroom.cfg_failed", exc_info=True)
        return None
```

- [ ] **Step 4: Edit `verdict.py`**

```python
from apps.ai.structured import run_structured
```

```python
def synthesize(
    subject_context: str,
    persona_args: list[dict],
    *,
    provider: str,
    api_key: str,
    model: str,
    base_url: str,
) -> WarRoomVerdict:
    args = "\n".join(f"- [{a.get('persona')}] {a.get('argument')}" for a in persona_args)
    user = f"SUBJECT:\n{subject_context}\n\nARGUMENTS:\n{args}\n\nDeliver your verdict."
    return run_structured(
        provider=provider,
        api_key=api_key,
        model=model,
        system=_SYSTEM,
        user=user,
        output_model=WarRoomVerdict,
        max_tokens=C.VERDICT_MAX_TOKENS,
        base_url=base_url,
    )
```

- [ ] **Step 5: Edit `strategy/tasks.py`**

Import: `from apps.strategy.warroom.services.convene import _synth_target`. In `run_debate`:

```python
    target = _synth_target()
    if target is None or not persona_args:
        run.status = "error"
        run.error = "Debate produced no arguments / no provider available for synthesis."
        run.save(update_fields=["status", "error"])
        return
    v = synthesize(
        ctx,
        persona_args,
        provider=target.provider,
        api_key=target.api_key,
        model=target.model,
        base_url=target.base_url,
    )
```

- [ ] **Step 6: Run the strategy suite**

Run: `$PYTEST apps/strategy`
Expected: PASS. If any other test still patches `_claude_cfg` (`grep -rn "_claude_cfg" backend/apps`), switch it to `_synth_target` returning a `StructuredTarget`.

- [ ] **Step 7: Commit**

```bash
cd $WT && git add backend/apps/strategy
LEFTHOOK=0 git commit -m "feat(strategy): war room verdict synthesizes on the resolved provider

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Narrative callers (coverage, post-mortem, regime, book)

**Files:**
- Modify: `backend/apps/strategy/coverage/services/revise.py:1-80`
- Modify: `backend/apps/thesis/services/postmortem.py:1-30`, `:94-152`
- Modify: `backend/apps/strategy/regime/services/narrative.py`
- Modify: `backend/apps/book/services/narrative.py`
- Test: `backend/apps/strategy/coverage/tests/test_revise.py`, `backend/apps/thesis/tests/test_postmortem.py:188-212`, `backend/apps/strategy/regime/tests/test_narrative.py`, `backend/apps/book/tests/test_narrative.py`

**Interfaces:**
- Consumes: Task 3 `resolve_structured_target`, `ensure_within_caps`, `run_structured`.

- [ ] **Step 1: Flip the "non-Claude skips" test and add one openai case per caller**

`thesis/tests/test_postmortem.py` — replace `test_run_postmortem_non_claude_provider_skips_ai` (line 188) with:

```python
@pytest.mark.django_db
def test_run_postmortem_openai_provider_runs_ai(thesis, fake_report):
    """Structured output has provider parity: an openai profile gets its narrative
    on openai, with the catalog default model when the config names none."""
    thesis.profile.default_provider = "openai"
    thesis.profile.save()
    cfg = ProviderConfig.objects.create(provider="openai", enabled=True)
    cfg.api_key = "sk-oai"
    cfg.save()

    pm = PostMortem.objects.create(
        thesis=thesis,
        horizon_days=7,
        due_at=thesis.opened_at + timedelta(days=7),
        status="scheduled",
    )
    _seed_bars("AAPL", thesis.opened_at, start_close=100.0, end_close=110.0, end=pm.due_at)

    with patch.object(pm_service, "run_structured", return_value=fake_report) as mock_run:
        run_postmortem(pm.id)

    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["provider"] == "openai"
    assert mock_run.call_args.kwargs["model"] == "gpt-5.6-sol"
    pm.refresh_from_db()
    assert pm.status == "done"
    assert pm.verdict == "correct"
    assert pm.report["summary"] == fake_report.summary
```

(`thesis`, `fake_report`, `_seed_bars`, `pm_service`, `PostMortem`, `ProviderConfig`, `timedelta`, `patch`, and `run_postmortem` are already imported/defined in the file.)

`strategy/coverage/tests/test_revise.py` — add:

```python
def test_openai_profile_runs_revision(profile, snapshot):
    profile.default_provider = "openai"
    profile.save()
    cfg = ProviderConfig.objects.create(provider="openai", enabled=True)
    cfg.api_key = "sk-oai"
    cfg.save()
    with patch(PATCH_TARGET, return_value=_draft(stance="bull", conviction=4)) as rs:
        revise_coverage("SPY", snapshot, profile=profile)
    assert rs.call_args.kwargs["provider"] == "openai"
    assert rs.call_args.kwargs["model"] == "gpt-5.6-sol"
```

`strategy/regime/tests/test_narrative.py` and `book/tests/test_narrative.py` (both alias their service module as `N`): rename `test_no_claude_config_returns_empty` to `test_no_provider_config_returns_empty` (body unchanged). In every test that patches the cap checks, replace the two lines

```python
    monkeypatch.setattr(N, "check_daily_cap", lambda *a, **k: None)
    monkeypatch.setattr(N, "check_monthly_cap", lambda *a, **k: None)
```

with

```python
    monkeypatch.setattr(N, "ensure_within_caps", lambda target: None)
```

(the service modules stop importing the two cap functions, so `monkeypatch.setattr` on those names would raise). Then add to the regime file:

```python
def test_openai_only_config_produces_summary(monkeypatch):
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(
        provider="openai", _api_key={"k": "sk-oai"}, default_model="gpt-5.6-sol"
    )
    captured = {}

    class _R:
        summary = "one paragraph"

    monkeypatch.setattr(N, "run_structured", lambda **kw: captured.update(kw) or _R())
    assert N.regime_narrative("Risk-Off", AXES, DRIVERS) == "one paragraph"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-5.6-sol"
```

and to the book file the same test with the body calling `N.book_narrative(DATA)`.

- [ ] **Step 2: Run to verify failure**

Run: `$PYTEST apps/thesis/tests/test_postmortem.py apps/strategy/coverage apps/strategy/regime apps/book`
Expected: the new/renamed tests FAIL (non-Claude providers skip today).

- [ ] **Step 3: Edit `strategy/coverage/services/revise.py`**

Imports: drop `DEFAULT_CLAUDE_MODEL`, `check_daily_cap`, `check_monthly_cap`, `ProviderConfig`, and the `claude_structured` import; keep `InvalidToken` and `CostCapExceededError`; add:

```python
from apps.ai.structured import ensure_within_caps, resolve_structured_target, run_structured
```

Replace the body from `provider_name = profile.default_provider` through the cap check with:

```python
    try:
        target = resolve_structured_target(profile=profile)
    except InvalidToken:
        # Undecryptable on a key/salt rotation — skip, never crash the caller.
        return None
    if target is None:
        return None
    try:
        ensure_within_caps(target)
    except CostCapExceededError as exc:
        log.info("coverage: cap exceeded, skipping %s revision: %s", ticker, exc)
        return None
```

Then:

```python
    note, created = CoverageNote.objects.get_or_create(
        ticker=ticker, defaults={"stance": "neutral", "conviction": 1}
    )
    try:
        draft = run_structured(
            provider=target.provider,
            api_key=target.api_key,
            model=target.model,
            system=build_system_prompt(profile, now=timezone.now()),
            user=_build_prompt(note, snapshot, ticker, target.provider, target.model),
            output_model=CoverageRevisionDraft,
            base_url=target.base_url,
        )
```

Module docstring: replace the last paragraph with "``run_structured`` (``apps.ai.structured``) has no ``MOCK_EXTERNAL`` short-circuit; tests patch the name bound here."

- [ ] **Step 4: Edit `thesis/services/postmortem.py`**

Imports: drop `DEFAULT_CLAUDE_MODEL`, `check_daily_cap`, `check_monthly_cap`, and the `claude_structured` import; add `from apps.ai.structured import ensure_within_caps, resolve_structured_target, run_structured`. Keep `ProviderConfig` only if still referenced elsewhere in the file (ruff F401 decides). Module docstring: "BEST-EFFORT generates an AI narrative via Claude structured output" → "BEST-EFFORT generates an AI narrative via structured output on the thesis's provider".

Replace the body of the narrative function from `provider_name = (` through the `run_structured(` call's arguments with:

```python
    try:
        target = resolve_structured_target(profile=thesis.profile)
    except InvalidToken:
        log.warning("postmortem %s: provider key could not be decrypted — skipping AI narrative", pm.id)
        return
    if target is None:
        log.warning("postmortem %s: no usable provider configured — skipping AI narrative", pm.id)
        return
    try:
        ensure_within_caps(target)
    except CostCapExceededError as exc:
        log.warning("postmortem %s: cost cap hit, skipping AI narrative — %s", pm.id, exc)
        return

    system = thesis.profile.style if thesis.profile else ""
    prompt = _build_prompt(thesis, pm, fwd, path)

    report = run_structured(
        provider=target.provider,
        api_key=target.api_key,
        model=target.model,
        system=system or "",
        user=prompt,
        output_model=PostMortemReport,
        base_url=target.base_url,
    )
```

The docstring's "On non-claude provider / no key / cap exceeded" becomes "On no usable provider / cap exceeded / undecryptable key". Note `resolve_structured_target(profile=None)` already covers the "thesis has no profile → first config" test (`test_run_postmortem_null_profile_falls_back_to_provider_config`).

- [ ] **Step 5: Edit `strategy/regime/services/narrative.py` and `book/services/narrative.py`**

Both files: imports become

```python
from apps.ai.cost import CostCapExceededError
from apps.ai.structured import ensure_within_caps, resolve_structured_target, run_structured
```

(drop `DEFAULT_CLAUDE_MODEL`, the cap-check imports, and the `claude_structured` import). Module docstrings: "(Claude)" → "(structured output on the default provider)"; "non-claude / no key" → "no usable provider". The function bodies become:

```python
def regime_narrative(composite: str, axes: dict, drivers: list[str]) -> str:
    try:
        target = resolve_structured_target()
        if target is None:
            return ""
        ensure_within_caps(target)
        report = run_structured(
            provider=target.provider,
            api_key=target.api_key,
            model=target.model,
            system="",
            user=_build_prompt(composite, axes, drivers),
            output_model=RegimeNarrative,
            base_url=target.base_url,
        )
        return (getattr(report, "summary", "") or "").strip()
    except CostCapExceededError as exc:
        log.warning("regime.narrative.cap_hit: %s", exc)
        return ""
    except Exception:
        log.warning("regime.narrative.failed", exc_info=True)
        return ""
```

and the same shape for `book_narrative(data)` with `_prompt(data)` / `BookNarrative` / the `book.narrative.*` log keys.

- [ ] **Step 6: Run the four suites**

Run: `$PYTEST apps/thesis apps/strategy apps/book`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd $WT && git add backend/apps/strategy/coverage backend/apps/thesis backend/apps/strategy/regime backend/apps/book
LEFTHOOK=0 git commit -m "feat: coverage, post-mortem, regime and book narratives run on the resolved provider

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Contracts, docs, full gate

**Files:**
- Modify: `pyproject.toml:167-196` (import-linter contract)
- Modify: `backend/apps/ai/providers/claude_structured.py:1-11` (docstring)
- Modify: `CLAUDE.md` — the "AI providers & capabilities" bullet on Claude-only features, the "Observer opt-in modes" consensus wording, the "Eval calibration loop" bullet, and the catalog bullet under "AI tokens, cost, caps & routing"
- Modify: `FEATURES.md` if it states structured output / consensus is Claude-only (`grep -n -i "claude-only\|claude only\|structured" FEATURES.md`)

- [ ] **Step 1: Tighten the import-linter contract**

In `pyproject.toml`, the contract comment and forbidden list become:

```toml
# The package re-export `from apps.ai.providers import get_provider`, the `base`
# Provider protocol, and `apps.ai.structured` (provider-neutral one-shot structured
# output + target resolution) are the PUBLIC surface. Instantiating a concrete
# impl or importing a per-vendor structured module elsewhere is the landmine.
```

```toml
forbidden_modules = [
    "apps.ai.providers.claude",
    "apps.ai.providers.openai",
    "apps.ai.providers.local",
    "apps.ai.providers.claude_structured",
    "apps.ai.providers.openai_structured",
]
```

Run: `$RUN -w /app web uv run lint-imports`
Expected: clean. A violation names a caller Tasks 4–8 missed; fix it to import from `apps.ai.structured`. (Tests under `apps/*/tests/` are source modules too: `apps/ai/tests/*` is inside `apps.ai` so it may import the private modules; any other app's test that imports `claude_structured` directly must switch to the facade.)

- [ ] **Step 2: Rewrite the `claude_structured.py` docstring**

```python
"""One-shot structured Claude run. Returns a parsed Pydantic model or raises.

The Anthropic implementation behind ``apps.ai.structured.run_structured`` for
Claude-family providers. Separate from the streaming ClaudeProvider so the two
return contracts (typed one-shot vs event stream) stay apart.

Uses ``messages.parse``, which takes an ``output_format`` Pydantic class and
returns a ``ParsedMessage`` whose ``.parsed_output`` is an instance of that class.
"""
```

- [ ] **Step 3: Update `CLAUDE.md`**

Under "### AI providers & capabilities", the first bullet becomes:

> **Tool use and structured output have provider parity; thinking/memory/files/citations are Claude-only.** One-shot structured output goes through `apps/ai/structured.py::run_structured(provider=…)` (Claude → `messages.parse`; OpenAI → `chat.completions.parse` strict JSON schema; Local → the same with a `json_object` + schema-in-prompt fallback, validated client-side) and records an `AIRun` under the real provider. Callers resolve their target via `resolve_structured_target(profile=, override_provider=)` (override → profile → calibration → first enabled; `local` needs a base URL, others a key) and cap-check with `ensure_within_caps`. **Never import `providers/claude_structured.py` or `providers/openai_structured.py` outside `apps.ai`** (import-linter). OpenAI/Local run tools via a tool-call loop emitting the same events. Tools opt-in per profile (`enable_tools`); OpenAI/Local also gated on `ProviderConfig.supports_tools`. **Enabling a Claude-only feature elsewhere warns-and-continues** — `run_ai_on_message` calls `capabilities.unsupported_features(...)`, writes a `capability_warning` message + `warning` WS event (excluded from `observer_timeline`).

Under "### Observer, triggers & scheduling", in the "Observer opt-in modes" bullet, `consensus` becomes: "`consensus` (with structured: the same `ObservationReport` on every usable provider, claude/openai/local; with fewer than 2 usable it records an honest single-provider shape)". Add to the same bullet: "`use_batch` is the only Claude-only mode (Messages Batches)."

Under "### Thesis, post-mortems & calibration", the eval bullet gains: "`manage.py aieval --model <id> --provider claude|openai|local` scores any provider; `EvalRun.model` identifies the vendor."

Under "### AI tokens, cost, caps & routing", add to the catalog bullet: "**The catalog is the only place an unknown model gets a budget or price** — a model id absent from `catalog.py` falls to a 40k payload budget and is billed at the provider's priciest row, so add new models there first. Fallback defaults are per provider (`default_model_for`: Opus 5 / GPT-5.6 Sol; `local` has none)."

- [ ] **Step 4: Run every gate against the worktree**

```bash
$RUN -w /app web uv run ruff check . && $RUN -w /app web uv run ruff format --check .
$RUN -w /app web uv run mypy backend/apps backend/config
$RUN -w /app web uv run lint-imports
$RUN -w /app web uv run deptry backend
docker run --rm -v "$WT:/src" -w /src semgrep/semgrep semgrep scan --error --quiet --config tools/semgrep/rules backend/
$PYTEST
```

Expected: all clean; pytest ≥ 2302 passed + the new tests, 0 failed. Fix anything red before committing.

- [ ] **Step 5: Commit**

```bash
cd $WT && git add pyproject.toml backend/apps/ai/providers/claude_structured.py CLAUDE.md FEATURES.md
LEFTHOOK=0 git commit -m "chore(ai): make the structured facade the only public path; document provider parity

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Live verification on the configured OpenAI key

**Files:** none (verification only; result goes in the final summary).

- [ ] **Step 1: Check whether an OpenAI key exists on the dev DB**

```bash
$RUN web uv run python manage.py shell -c "from apps.secrets.models import ProviderConfig; c=ProviderConfig.objects.filter(provider='openai').first(); print('openai cfg:', bool(c), 'key:', bool(c and c.api_key), 'model:', c.default_model if c else None)"
```

If it prints `key: False`, stop here and report "live OpenAI verification skipped: no key configured".

- [ ] **Step 2: One real `ObservationReport` parse through the facade**

```bash
$RUN web uv run python manage.py shell -c "
from apps.ai.structured import run_structured, resolve_structured_target
from apps.observer.schemas import ObservationReport
t = resolve_structured_target(override_provider='openai', override_model='gpt-5.6-sol')
r = run_structured(provider=t.provider, api_key=t.api_key, model=t.model, base_url=t.base_url,
    system='You are a trading analyst. Strictly observational.',
    user='SPY 660.10 (+0.4%), QQQ +0.9%, RSP flat, VIX 14.2 (front/second 15.1/16.0), 10y +6bp, DXY +0.3%. Give a structured observation.',
    output_model=ObservationReport)
print(r.model_dump_json(indent=1)[:600])
from apps.threads.models import AIRun
print(AIRun.objects.filter(provider='openai').order_by('-id').values('model','input_tokens','output_tokens','cost_usd').first())
"
```

Expected: a parsed report prints and the last `AIRun` row is `provider=openai`, `model=gpt-5.6-sol`, `cost_usd > 0`. A `BadRequestError` naming a schema keyword means strict mode rejected a Pydantic feature — apply Task 3 Step 3b's fix to that model, re-run the strict-schema test, and retry.

- [ ] **Step 3: Record the outcome** in the final summary (pass / skipped-no-key / failed-with-error) and delete nothing: the `AIRun` row is real spend and stays in the ledger.
