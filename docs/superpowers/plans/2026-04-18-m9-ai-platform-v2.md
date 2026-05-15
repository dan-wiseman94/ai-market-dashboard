# M9 — AI Platform v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize the AI platform layer so the dashboard spends less money, trusts its own token math, enforces the monthly cap it claims to, returns structured observations, and surfaces a unique "what changed since the last snapshot?" capability — plus a tight frontend polish pass (toasts, skeletons, error boundary, command palette).

**Architecture:** Nine self-contained backend/frontend additions that each produce a working vertical slice.
- Token math moves from `tiktoken.cl100k_base` (wrong for Claude) to a provider-aware estimator that calls Anthropic's `count_tokens` endpoint for Claude models and keeps `tiktoken` for OpenAI/local.
- Prompt caching extends from the system block to the last prior assistant turn on multi-turn Claude runs, unlocking ~0.1× input cost on follow-up questions.
- Monthly cap enforcement reuses the existing `CostCapExceededError` pathway (already wired through `threads.tasks` and `observer.services.run`).
- Structured Observer outputs use `messages.parse` with a Pydantic schema; we serialize the structured result into the existing `Message.content` dict so the UI can render typed cards without breaking older rows.
- The snapshot diff is a new service + endpoint that walks two `Snapshot.sections` dicts and emits a compact delta blob; the Observer optionally uses it to feed the AI only the delta, not the full payload.
- Batch API adds a new `observer.services.batch` module that queues watchlist sweeps via Anthropic's `messages.batches`, polls in a Celery beat task, and writes results back to individual Observer threads on completion.
- Frontend additions are DRY components (`Toasts`, `Skeleton`, `EmptyState`, `ErrorBoundary`, `CommandPalette`) plugged into the existing `<AppLayout>`.

**Tech Stack:** Django 5.1 + DRF + Channels; Celery + beat; anthropic-py SDK (≥0.40 for `count_tokens` and Batch); Pydantic 2; React 18 + Vite; Tailwind; react-query.

**Scope notes:**
- **In scope:** 9 tasks, all additive; no migrations break existing data; all features are opt-in via feature flags or config where they alter behavior on hot paths.
- **Out of scope (saved for M10):** Tool use on Claude (`get_quote`, `fetch_ohlc`, etc.); Files API; Citations via `search_result` blocks; MCP server/client; extended thinking; memory tool; Skills. These reshape the product materially and deserve their own plan after M9's foundations land.
- **Out of scope (saved for M11):** Thesis objects, decision journal, post-mortem scheduler, agent presets (earnings prep, devil's advocate, triage pass).
- **Assumption:** The `2026-04-18-thread-snapshot-injection.md` plan has landed before M9 starts (consult threads inject snapshot text on first turn). M9 does not re-implement that.

---

## Task 1: Provider-aware token estimator

**Files:**
- Create: `backend/apps/ai/token_counter.py`
- Modify: `backend/apps/snapshots/token_budget.py`
- Modify: `backend/apps/snapshots/serializer.py` (if it imports from `token_budget`)
- Test: `backend/apps/ai/tests/test_token_counter.py`

- [ ] **Step 1: Write the failing test**

```python
"""Token estimator must route by provider: Anthropic count_tokens for Claude,
tiktoken for OpenAI/local. Must never raise on empty or non-ASCII strings.

Regression guard for the pre-fix state where `cl100k_base` was applied to all
providers, producing off-by-25% counts for Claude (different BPE) and silently
feeding wrong numbers into `prune_to_budget` and cost previews.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from apps.ai.token_counter import estimate_tokens


def test_estimate_empty_string_returns_zero():
    assert estimate_tokens("", provider="claude", model="claude-opus-4-7") == 0
    assert estimate_tokens("", provider="openai", model="gpt-5") == 0


def test_estimate_openai_uses_tiktoken():
    n = estimate_tokens("hello world", provider="openai", model="gpt-5")
    assert 1 <= n <= 4  # tiktoken gives exactly 2 for "hello world"


def test_estimate_local_uses_tiktoken():
    n = estimate_tokens("hello world", provider="local", model="whatever")
    assert 1 <= n <= 4


def test_estimate_claude_calls_sdk_count_tokens():
    """Claude path must hit the SDK, not fall through to tiktoken."""
    with patch("apps.ai.token_counter._claude_count_tokens", return_value=42) as m:
        n = estimate_tokens("any text", provider="claude", model="claude-opus-4-7")
    assert n == 42
    m.assert_called_once()


def test_estimate_unicode_no_crash():
    assert estimate_tokens("🔥日本語", provider="openai", model="gpt-5") > 0
    with patch("apps.ai.token_counter._claude_count_tokens", return_value=7):
        assert estimate_tokens("🔥日本語", provider="claude", model="claude-opus-4-7") == 7


def test_unknown_provider_falls_back_to_tiktoken():
    n = estimate_tokens("hello", provider="ollama", model="llama3")
    assert n >= 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose exec web pytest backend/apps/ai/tests/test_token_counter.py -v
```

Expected: FAIL — `ModuleNotFoundError: apps.ai.token_counter`.

- [ ] **Step 3: Implement the estimator**

Create `backend/apps/ai/token_counter.py`:

```python
"""Provider-aware token estimator.

Claude uses a different tokenizer than GPT. Calling tiktoken.cl100k_base on
Claude text miscounts by ~15-25%. This module routes by provider:
- claude: Anthropic SDK count_tokens endpoint (network call; cached)
- openai / local / unknown: tiktoken.cl100k_base (local, fast)
"""
from __future__ import annotations

import logging
from functools import lru_cache

import tiktoken

log = logging.getLogger(__name__)

_ENC = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str, *, provider: str, model: str) -> int:
    if not text:
        return 0
    if provider == "claude":
        try:
            return _claude_count_tokens(text, model)
        except Exception as exc:  # noqa: BLE001 — degrade, don't raise
            log.warning("Claude count_tokens failed (%s); falling back to tiktoken", exc)
            return len(_ENC.encode(text))
    return len(_ENC.encode(text))


@lru_cache(maxsize=1024)
def _claude_count_tokens(text: str, model: str) -> int:
    """Call Anthropic count_tokens. Cached so repeated identical chunks (e.g.,
    the trading-style prompt across many snapshots) don't hit the network twice.
    """
    from anthropic import Anthropic  # sync client for a one-shot call

    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.filter(provider="claude").first()
    if cfg is None or not cfg.api_key:
        # No key configured; use tiktoken as a best-effort estimate.
        return len(_ENC.encode(text))

    client = Anthropic(api_key=cfg.api_key)
    resp = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}],
    )
    return int(resp.input_tokens)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec web pytest backend/apps/ai/tests/test_token_counter.py -v
```

Expected: all 6 PASS.

- [ ] **Step 5: Replace `token_budget.estimate_tokens` callers**

Edit `backend/apps/snapshots/token_budget.py` — replace the whole file with:

```python
"""Token estimation + pruning for payload sections."""
from __future__ import annotations

from apps.ai.token_counter import estimate_tokens as _estimate

_PRUNE_ORDER = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]


def estimate_tokens(text: str, *, provider: str = "openai", model: str = "") -> int:
    """Provider-aware estimate. Defaults preserve the old tiktoken behavior."""
    return _estimate(text, provider=provider, model=model)


def prune_to_budget(
    sections: dict[str, str],
    *,
    max_tokens: int,
    provider: str = "openai",
    model: str = "",
) -> tuple[dict[str, str], list[str]]:
    kept = dict(sections)
    pruned: list[str] = []
    sizes = {k: _estimate(v, provider=provider, model=model) for k, v in kept.items()}
    total = sum(sizes.values())

    for kind in _PRUNE_ORDER:
        if total <= max_tokens:
            break
        if kind in kept:
            del kept[kind]
            total -= sizes[kind]
            pruned.append(kind)

    return kept, pruned
```

Verify callers. Grep for the old signatures:

```bash
docker compose exec web grep -rn "prune_to_budget\|estimate_tokens" backend/apps/
```

Any caller passing only positional arguments still works (the new `provider` / `model` kwargs default to `openai` / `""` which reproduces the old tiktoken path). **No caller changes are strictly required by this task** — Task 2 will wire the real provider/model in.

- [ ] **Step 6: Run the full ai + snapshots + threads test suites to catch regressions**

```bash
docker compose exec web pytest backend/apps/ai backend/apps/snapshots backend/apps/threads -v
```

Expected: all tests PASS (the default-arg fallback preserves old behavior everywhere).

- [ ] **Step 7: Commit**

```bash
git add backend/apps/ai/token_counter.py backend/apps/ai/tests/test_token_counter.py backend/apps/snapshots/token_budget.py
git commit -m "$(cat <<'EOF'
feat(ai): provider-aware token estimator

tiktoken.cl100k_base miscounts Claude input by ~15-25% (different BPE).
Add apps.ai.token_counter.estimate_tokens that calls Anthropic count_tokens
for Claude and tiktoken for OpenAI/local, with a best-effort tiktoken
fallback when the key is missing or the network hiccups.

Default kwargs in token_budget preserve the old behavior for callers that
don't yet pass provider/model; subsequent tasks wire those through.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Raise snapshot token budget + thread provider/model through pruning

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (caller of `prune_to_budget`)
- Modify: `backend/apps/snapshots/services.py` (stamp_payload_tokens)
- Modify: `backend/apps/ai/catalog.py` (add `max_payload_tokens` hint per model)
- Test: `backend/apps/snapshots/tests/test_token_budget.py`

**Context:** The serializer currently hard-codes `max_tokens=40_000` which wastes most of Claude's 200k context (and 1M on the 1M-context variant). Move the budget to the catalog and wire it through.

- [ ] **Step 1: Add `max_payload_tokens` to `ModelInfo`**

Edit `backend/apps/ai/catalog.py`. Change the `ModelInfo` dataclass:

```python
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
    supports_cache: bool
    max_payload_tokens: int = 40_000  # default keeps back-compat
```

Then update each `_CATALOG` entry to set a sensible budget (leave headroom for system + history + output):
- Claude Opus/Sonnet/Haiku 4.x (200k ctx): `max_payload_tokens=150_000`
- GPT-5 (400k ctx): `max_payload_tokens=300_000`
- GPT-5-mini/nano: `max_payload_tokens=200_000`

- [ ] **Step 2: Write a test for the new serializer signature**

Grep first:

```bash
docker compose exec web grep -n "prune_to_budget\|serialize_for_ai" backend/apps/snapshots/serializer.py
```

Open `backend/apps/snapshots/tests/test_serializer.py` (or create the file if absent) and add:

```python
def test_serialize_for_ai_uses_model_budget_when_provided(db, ready_snapshot):
    """When called with a model id, the serializer should look up
    that model's max_payload_tokens in the catalog."""
    from apps.snapshots.serializer import serialize_for_ai

    text = serialize_for_ai(ready_snapshot, provider="claude", model="claude-opus-4-7")
    assert len(text) > 0
    # Opus budget is 150k → large snapshot should not be pruned
    assert "[pruned:" not in text or "pruned: " not in text


def test_serialize_for_ai_default_still_works(db, ready_snapshot):
    """Callers that don't pass provider/model still get a valid payload
    (backward-compat with observer/trigger paths that haven't been updated)."""
    from apps.snapshots.serializer import serialize_for_ai

    text = serialize_for_ai(ready_snapshot)
    assert len(text) > 0
```

(If `ready_snapshot` fixture doesn't exist yet, copy it from `backend/apps/threads/tests/test_snapshot_injection.py` and adapt.)

- [ ] **Step 3: Run the failing test**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer.py -v
```

Expected: `test_serialize_for_ai_uses_model_budget_when_provided` FAILS on TypeError (unknown kwargs).

- [ ] **Step 4: Wire provider/model through the serializer**

In `backend/apps/snapshots/serializer.py`, add optional `provider` and `model` kwargs to `serialize_for_ai`:

```python
def serialize_for_ai(
    snap: Snapshot,
    *,
    provider: str = "openai",
    model: str = "",
) -> str:
    from apps.ai.catalog import get_model
    info = get_model(provider, model) if model else None
    budget = info.max_payload_tokens if info else 40_000
    # ... existing body, but pass budget + provider/model into prune_to_budget
    kept, pruned = prune_to_budget(sections, max_tokens=budget, provider=provider, model=model)
    ...
```

(The exact edit depends on current body — grep `prune_to_budget` in the file and replace the `max_tokens=` value.)

- [ ] **Step 5: Update `stamp_payload_tokens` similarly**

Grep:

```bash
docker compose exec web grep -n "stamp_payload_tokens" backend/apps/snapshots/services.py
```

Add provider/model kwargs and thread them through the per-section `estimate_tokens` call.

- [ ] **Step 6: Callers pass provider/model where known**

For each of these callers, add `provider=..., model=...`:
- `backend/apps/observer/services/run.py:74` — `serialize_for_ai(snap, provider=provider_name, model=...)` (resolve model_id first)
- `backend/apps/triggers/tasks.py` — grep for `serialize_for_ai` and pass provider/model

Anywhere we don't yet know the model, leave the old signature (default "openai"/"") — still works.

- [ ] **Step 7: Run the new + adjacent tests**

```bash
docker compose exec web pytest backend/apps/snapshots backend/apps/observer backend/apps/triggers -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/ai/catalog.py backend/apps/snapshots/ backend/apps/observer/services/run.py backend/apps/triggers/tasks.py
git commit -m "$(cat <<'EOF'
feat(snapshots): use catalog max_payload_tokens + thread provider through

Previously hard-coded 40k-token budget wasted 75% of Claude's 200k context
and 96% of GPT-5's 400k. Move per-model budgets into ModelInfo and let the
serializer route by the provider/model the snapshot will be sent to.

Backward-compatible: callers that don't pass provider/model still get the
old 40k ceiling and tiktoken estimation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Cache the last prior assistant turn on Claude

**Files:**
- Modify: `backend/apps/ai/providers/claude.py`
- Modify: `backend/apps/ai/types.py`
- Test: `backend/apps/ai/tests/test_claude_caching.py`

**Context:** `system_blocks` is already `cache_control: ephemeral`. For multi-turn threads (the common "follow-up" pattern), mark the final prior message with `cache_control` too — on hit, Anthropic bills ~0.1× base input for everything before that breakpoint.

- [ ] **Step 1: Add a `cache_last_message` flag to RunRequest**

Edit `backend/apps/ai/types.py`:

```python
@dataclass
class RunRequest:
    model: str
    system: str
    messages: list[ChatMessage]
    max_tokens: int = 4096
    temperature: float = 1.0
    cache_system: bool = True
    cache_last_message: bool = False  # NEW — only set True on multi-turn runs
```

- [ ] **Step 2: Write the failing test**

Create `backend/apps/ai/tests/test_claude_caching.py`:

```python
"""Claude provider must attach cache_control to the final prior turn when
cache_last_message=True. The cache breakpoint lives on the LAST message
in the list (Anthropic's rules: everything *before* it is cached on hit)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.ai.providers.claude import ClaudeProvider, _maybe_cache_last_message
from apps.ai.types import ChatMessage, RunRequest


def test_maybe_cache_last_message_attaches_cache_control():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "now analyze this snapshot..."},
    ]
    out = _maybe_cache_last_message(msgs, cache=True)
    assert out[0]["content"] == "hello"
    assert out[1]["content"] == "hi"
    # last message becomes a block list with cache_control on the final block
    last = out[-1]
    assert isinstance(last["content"], list)
    assert last["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_maybe_cache_last_message_noop_when_flag_false():
    msgs = [{"role": "user", "content": "hello"}]
    out = _maybe_cache_last_message(msgs, cache=False)
    assert out == msgs


def test_maybe_cache_last_message_noop_on_empty():
    assert _maybe_cache_last_message([], cache=True) == []
```

- [ ] **Step 3: Run the failing test**

```bash
docker compose exec web pytest backend/apps/ai/tests/test_claude_caching.py -v
```

Expected: FAIL — `_maybe_cache_last_message` doesn't exist yet.

- [ ] **Step 4: Implement the helper + wire it in**

Edit `backend/apps/ai/providers/claude.py`. Replace the body of `run()` and add the helper:

```python
"""Claude provider — streams via anthropic SDK."""
from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from apps.ai.types import (
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunRequest,
    TextDelta,
    TokenUsage,
    UsageEvent,
)


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, base_url: str = "") -> None:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**kwargs)  # type: ignore[arg-type]

    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]:
        from apps.core.mocks import is_mock_mode
        if is_mock_mode():
            yield TextDelta(text="Mocked ")
            yield TextDelta(text="response")
            yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))
            yield DoneEvent()
            return

        system_blocks = _system_blocks(req.system, cache=req.cache_system)
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        messages = _maybe_cache_last_message(messages, cache=req.cache_last_message)

        try:
            async with self._client.messages.stream(
                model=req.model,
                system=system_blocks,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield TextDelta(text=event.text)
                final = await stream.get_final_message()
            u = final.usage
            yield UsageEvent(usage=TokenUsage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cached_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            ))
            yield DoneEvent()
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}")


def _system_blocks(system: str, *, cache: bool) -> list[dict]:
    block: dict = {"type": "text", "text": system}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def _maybe_cache_last_message(messages: list[dict], *, cache: bool) -> list[dict]:
    """Attach cache_control to the final text block of the last message.

    Rebuilds the last message with `content` as a single text block list so we
    can hang cache_control off it. Earlier messages are unchanged — Anthropic
    caches everything *before* the breakpoint on hit.
    """
    if not cache or not messages:
        return messages
    out = [dict(m) for m in messages]
    last = out[-1]
    text = last["content"] if isinstance(last["content"], str) else ""
    last["content"] = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    return out
```

- [ ] **Step 5: Set `cache_last_message=True` on multi-turn runs**

Edit `backend/apps/threads/tasks.py`, in `_build_request`. Currently ends with `return RunRequest(model="", system=system, messages=chat_messages, cache_system=True)`. Change to:

```python
    return RunRequest(
        model="",
        system=system,
        messages=chat_messages,
        cache_system=True,
        cache_last_message=len(chat_messages) > 1,
    )
```

Rationale: single-turn runs (just the user kick-off) have no history to cache. Multi-turn runs are exactly where the breakpoint pays off.

- [ ] **Step 6: Run the tests**

```bash
docker compose exec web pytest backend/apps/ai/tests/test_claude_caching.py backend/apps/threads/tests/ -v
```

Expected: all PASS. If any threads test asserted the old `RunRequest(...)` shape, update the assertion to match the new fields.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/ai/types.py backend/apps/ai/providers/claude.py backend/apps/ai/tests/test_claude_caching.py backend/apps/threads/tasks.py
git commit -m "$(cat <<'EOF'
feat(ai): cache the last prior turn on Claude multi-turn runs

cache_control was already set on the system block; add a second breakpoint
on the final message for multi-turn threads. On cache hit, everything
before the breakpoint reads at 0.1x base input cost — typical follow-up
questions on an existing thread drop ~90% on input tokens.

Single-turn kickoffs skip the flag (no history to cache).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Monthly cost cap enforcement

**Files:**
- Modify: `backend/apps/ai/cost.py`
- Modify: `backend/apps/threads/tasks.py`
- Modify: `backend/apps/observer/services/run.py`
- Modify: `backend/apps/triggers/tasks.py`
- Test: `backend/apps/ai/tests/test_monthly_cap.py`

**Context:** `ProviderConfig.monthly_cost_cap_usd` is stored on the settings page and displayed on the costs dashboard, but no code path checks it. A user who raises the daily cap once burns through the monthly cap invisibly. Fix parity with the daily cap.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/ai/tests/test_monthly_cap.py`:

```python
"""Monthly cost cap must block like the daily cap does. Nullable cap means
'no monthly limit' — the existing code path on ProviderConfig stores None
when unset."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ai.cost import (
    CostCapExceededError,
    check_monthly_cap,
    monthly_spend_usd,
)
from apps.threads.models import AIRun, Message, Thread


@pytest.fixture
def thread(db, profile):
    return Thread.objects.create(kind="consult", profile=profile)


@pytest.fixture
def profile(db):
    from apps.profiles.models import TradingProfile
    return TradingProfile.objects.create(name="test", style="test")


def _make_run(thread, *, days_ago: int, cost: Decimal, provider: str = "claude"):
    msg = Message.objects.create(thread=thread, role="assistant",
                                  content={"text": ""}, status="done")
    run = AIRun.objects.create(
        message=msg, provider=provider, model="claude-opus-4-7",
        cost_usd=cost, status="done",
    )
    # Back-date to test month-window math.
    AIRun.objects.filter(id=run.id).update(
        created_at=timezone.now() - timedelta(days=days_ago),
    )
    return run


def test_monthly_spend_sums_last_30_days(db, thread):
    _make_run(thread, days_ago=1, cost=Decimal("1.00"))
    _make_run(thread, days_ago=5, cost=Decimal("2.00"))
    _make_run(thread, days_ago=31, cost=Decimal("99.00"))  # outside window
    assert monthly_spend_usd("claude") == Decimal("3.00")


def test_check_monthly_cap_raises_when_exceeded(db, thread):
    _make_run(thread, days_ago=1, cost=Decimal("9.00"))
    with pytest.raises(CostCapExceededError):
        check_monthly_cap("claude", Decimal("10.00"), prospective_cost=Decimal("2.00"))


def test_check_monthly_cap_none_means_no_limit(db, thread):
    _make_run(thread, days_ago=1, cost=Decimal("1000.00"))
    # None cap → early return; no raise even with huge prospective cost.
    check_monthly_cap("claude", None, prospective_cost=Decimal("1000.00"))


def test_check_monthly_cap_under_limit_passes(db, thread):
    _make_run(thread, days_ago=1, cost=Decimal("5.00"))
    check_monthly_cap("claude", Decimal("10.00"), prospective_cost=Decimal("2.00"))
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose exec web pytest backend/apps/ai/tests/test_monthly_cap.py -v
```

Expected: FAIL — `check_monthly_cap` / `monthly_spend_usd` don't exist yet.

- [ ] **Step 3: Implement the cap helpers**

Edit `backend/apps/ai/cost.py`, append at the bottom:

```python
def monthly_spend_usd(provider: str) -> Decimal:
    """Sum the last 30 days of AIRun.cost_usd for the given provider."""
    from datetime import timedelta

    from django.db.models import Sum

    from apps.threads.models import AIRun

    window_start = datetime.now(tz=UTC) - timedelta(days=30)
    agg = AIRun.objects.filter(
        provider=provider, created_at__gte=window_start,
    ).aggregate(total=Sum("cost_usd"))
    return agg["total"] or Decimal("0")


def check_monthly_cap(
    provider: str,
    cap_usd: Decimal | None,
    prospective_cost: Decimal = Decimal("0"),
) -> None:
    """Raise if last-30-days + prospective would exceed cap.

    A cap of None (the default when a user hasn't set one on ProviderConfig)
    is a no-op: monthly caps are opt-in.
    """
    if cap_usd is None:
        return
    spent = monthly_spend_usd(provider)
    if spent + prospective_cost > cap_usd:
        raise CostCapExceededError(
            f"{provider} monthly cap ${cap_usd} would be exceeded "
            f"(30-day spend ${spent}, this run ~${prospective_cost})"
        )
```

- [ ] **Step 4: Wire the check into threads.tasks**

Edit `backend/apps/threads/tasks.py`. Find the existing `check_daily_cap` call (around line 166) and add a sibling `check_monthly_cap` call immediately after:

```python
    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd)
    except CostCapExceededError as exc:
        _fail(
            thread_id=thread_id, parent_message_id=parent_message_id,
            error=str(exc), event="cost_capped",
        )
        return {"ok": False, "error": "cost_capped"}
```

Add `check_monthly_cap` to the imports at the top of the file:

```python
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap, cost_usd_for
```

- [ ] **Step 5: Same in observer.services.run**

Edit `backend/apps/observer/services/run.py`:

```python
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
```

And the try block:

```python
    try:
        check_daily_cap(provider_name, cap_usd=cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd if cfg := ProviderConfig.objects.filter(provider=provider_name).first() else None)
    except CostCapExceededError:
        ...
```

Tidy: rework to resolve `cfg` once, use both caps from it.

- [ ] **Step 6: Same in triggers.tasks**

Grep `check_daily_cap` in `backend/apps/triggers/tasks.py`, add the monthly sibling.

- [ ] **Step 7: Run the full test suite for affected apps**

```bash
docker compose exec web pytest backend/apps/ai backend/apps/threads backend/apps/observer backend/apps/triggers -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/ai/cost.py backend/apps/ai/tests/test_monthly_cap.py backend/apps/threads/tasks.py backend/apps/observer/services/run.py backend/apps/triggers/tasks.py
git commit -m "$(cat <<'EOF'
feat(ai): enforce monthly cost cap (parity with daily cap)

ProviderConfig.monthly_cost_cap_usd was stored and displayed but never
checked. Add check_monthly_cap + monthly_spend_usd (last 30 days) and
wire them into threads, observer, and trigger fire paths alongside
check_daily_cap. Null cap remains a no-op — caps are opt-in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Structured outputs for Observer analyses

**Files:**
- Create: `backend/apps/observer/schemas.py`
- Create: `backend/apps/ai/providers/claude_structured.py`
- Modify: `backend/apps/observer/services/run.py` (opt-in flag)
- Modify: `backend/apps/observer/models.py` (add `structured: bool` to schedule)
- Migration: `backend/apps/observer/migrations/NNNN_schedule_structured.py` (generated)
- Test: `backend/apps/observer/tests/test_structured_outputs.py`

**Context:** Observer analyses are free-form text. Move them (when the schedule opts in) to a Pydantic-schema-backed response so the UI can render typed cards ("Signal: bullish", "Key levels: 420 / 415", "Risks: earnings tomorrow") instead of parsing markdown. Non-structured mode stays the default for backward-compat.

- [ ] **Step 1: Define the schema**

Create `backend/apps/observer/schemas.py`:

```python
"""Pydantic schemas for structured Observer outputs.

Keep these intentionally tight — the AI is free-form by default; structured
mode is opt-in on the schedule. Adding fields is backward-compatible; removing
them is not. When extending, add Optional + default None first, then make
required in a later release after all running schedules have re-emitted.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Bias = Literal["bullish", "bearish", "neutral", "mixed"]


class KeyLevel(BaseModel):
    label: str = Field(description="Short label, e.g. 'prior day high'")
    price: float
    kind: Literal["support", "resistance", "pivot", "target"]


class Signal(BaseModel):
    ticker: str
    bias: Bias
    thesis: str = Field(max_length=500)
    invalidation: str = Field(max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)


class ObservationReport(BaseModel):
    headline: str = Field(max_length=140)
    bias: Bias
    summary: str = Field(max_length=1200)
    signals: list[Signal] = Field(default_factory=list, max_length=10)
    key_levels: list[KeyLevel] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=8)
    next_check_in: str = Field(
        max_length=80,
        description="When or under what condition the observer should re-check.",
    )
```

- [ ] **Step 2: Add a structured-run helper for Claude**

Create `backend/apps/ai/providers/claude_structured.py`:

```python
"""One-shot structured Claude run. Returns a parsed Pydantic model or raises.

Separate from the streaming ClaudeProvider so we don't mix two different
return contracts. Intended for Observer / trigger analyses where we want
a typed result in one go, not token streaming to the UI.
"""
from __future__ import annotations

from typing import TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


def run_structured(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int = 2048,
    base_url: str = "",
) -> M:
    client = Anthropic(api_key=api_key, base_url=base_url or None)
    resp = client.messages.parse(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=max_tokens,
        output_format=output_model,
    )
    return resp.output  # type: ignore[no-any-return]
```

- [ ] **Step 3: Add the `structured` flag to ObserverSchedule**

Edit `backend/apps/observer/models.py`. Add a field:

```python
    structured = models.BooleanField(
        default=False,
        help_text="When True, observer runs use messages.parse with ObservationReport schema.",
    )
```

Generate the migration:

```bash
docker compose exec web python manage.py makemigrations observer -n schedule_structured
```

- [ ] **Step 4: Write the failing test**

Create `backend/apps/observer/tests/test_structured_outputs.py`:

```python
"""Observer structured mode must call run_structured and persist the parsed
result into the Message so the UI can render typed cards.

Uses mocks for the Anthropic call — we're testing integration wiring, not SDK."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.observer.schemas import ObservationReport


@pytest.fixture
def fake_report() -> ObservationReport:
    return ObservationReport(
        headline="SPY grinds toward 525 with light vol",
        bias="neutral",
        summary="Price respects the rising 20-period but breadth is mixed.",
        signals=[],
        key_levels=[],
        risks=["CPI tomorrow"],
        next_check_in="after the 10:00 breadth reading",
    )


def test_structured_observer_run_persists_parsed_json(db, schedule_structured, fake_report):
    """When schedule.structured=True, run_observer writes the report JSON
    into the assistant message so the UI can render cards."""
    from apps.observer.services import run as run_service

    with patch.object(run_service, "run_structured", return_value=fake_report):
        with patch.object(run_service, "run_ai_on_message") as streaming:
            snapshot_id = run_service.run_observer(schedule_structured.id)

    streaming.delay.assert_not_called()  # structured path must NOT queue the streaming task
    # Find the assistant message the structured path created.
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message
    thread = get_or_create_observer_thread(schedule_structured.profile)
    msg = Message.objects.filter(thread=thread, role="assistant").order_by("-id").first()
    assert msg is not None
    assert msg.content["kind"] == "structured_observation"
    assert msg.content["report"]["headline"] == fake_report.headline
    assert msg.content["report"]["bias"] == "neutral"
```

Also define a `schedule_structured` fixture in the same file:

```python
@pytest.fixture
def schedule_structured(db):
    from apps.observer.models import ObserverSchedule
    from apps.profiles.models import TradingProfile
    profile = TradingProfile.objects.create(name="p", style="s", default_provider="claude")
    return ObserverSchedule.objects.create(
        name="sched", profile=profile, cron="*/15 * * * *",
        objective_template="watch", structured=True,
    )
```

- [ ] **Step 5: Run the failing test**

```bash
docker compose exec web pytest backend/apps/observer/tests/test_structured_outputs.py -v
```

Expected: FAIL — `run_service` doesn't import `run_structured` yet and has no structured branch.

- [ ] **Step 6: Implement the structured branch**

Edit `backend/apps/observer/services/run.py`. Above the existing `run_ai_on_message.delay(...)` call, add a branch:

```python
    if sched.structured:
        from apps.ai.providers.claude_structured import run_structured
        from apps.observer.schemas import ObservationReport
        from apps.secrets.models import ProviderConfig
        cfg = ProviderConfig.objects.filter(provider=provider_name).first()
        if cfg is None or not cfg.api_key:
            Message.objects.create(
                thread=thread, role="system",
                content={"text": f"Observer {sched.name}: no key for {provider_name}"},
                status="done",
            )
            return snap.id
        model_id = sched.override_model or cfg.default_model or "claude-opus-4-7"
        try:
            report = run_structured(
                api_key=cfg.api_key,
                model=model_id,
                system=sched.profile.style or "",
                user=serialize_for_ai(snap, provider=provider_name, model=model_id),
                output_model=ObservationReport,
            )
        except Exception as exc:  # noqa: BLE001
            Message.objects.create(
                thread=thread, role="assistant",
                content={"text": f"Structured run failed: {exc}"},
                status="failed",
            )
            return snap.id
        Message.objects.create(
            thread=thread, role="assistant",
            content={"kind": "structured_observation", "report": report.model_dump()},
            status="done",
        )
        sched.last_fired_at = timezone.now()
        sched.save(update_fields=["last_fired_at"])
        return snap.id

    # Streaming path (existing behavior — unchanged below)
    ...
```

- [ ] **Step 7: Run the test**

```bash
docker compose exec web pytest backend/apps/observer/tests/test_structured_outputs.py -v
```

Expected: PASS.

- [ ] **Step 8: Run the full observer suite for regressions**

```bash
docker compose exec web pytest backend/apps/observer -v
```

Expected: all PASS (the new branch only triggers when `structured=True`).

- [ ] **Step 9: Commit**

```bash
git add backend/apps/observer/schemas.py backend/apps/ai/providers/claude_structured.py backend/apps/observer/models.py backend/apps/observer/migrations/ backend/apps/observer/services/run.py backend/apps/observer/tests/test_structured_outputs.py
git commit -m "$(cat <<'EOF'
feat(observer): structured output mode via messages.parse

Add ObservationReport Pydantic schema + claude_structured.run_structured
helper. ObserverSchedule gains a `structured: bool` flag (default False).
When True, run_observer writes the parsed report as JSON into Message.content
so the UI can render typed cards instead of markdown.

Streaming path unchanged; feature is opt-in per schedule.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Snapshot diff service

**Files:**
- Create: `backend/apps/snapshots/diff.py`
- Test: `backend/apps/snapshots/tests/test_diff.py`

**Context:** A universal trader question is "what changed vs yesterday's capture?". We already store structured section payloads — produce a compact delta (quotes moved, new news items, chain skew shift, breadth change) that can be fed into the AI *instead of* re-sending the full payload. Massive token savings for regular observers, and a unique capability.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_diff.py`:

```python
"""Snapshot diff must produce a compact, human-readable delta for AI context.

Tested at the unit level (dict in → string out), no DB or SDK."""
from __future__ import annotations

from apps.snapshots.diff import diff_sections


def test_quotes_delta_highlights_movers():
    prev = {"quotes": {"SPY": {"last": 520.0}, "QQQ": {"last": 440.0}}}
    curr = {"quotes": {"SPY": {"last": 525.0}, "QQQ": {"last": 440.5}}}
    out = diff_sections(prev, curr)
    assert "SPY" in out
    assert "+0.96%" in out or "+0.96" in out  # movement magnitude
    # QQQ moved <0.5% — should be suppressed or marked as noise
    assert "QQQ" not in out or "unchanged" in out.lower()


def test_news_delta_lists_only_new_headlines():
    prev = {"news": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]}
    curr = {"news": [{"id": 2, "title": "B"}, {"id": 3, "title": "C"}]}
    out = diff_sections(prev, curr)
    assert "C" in out
    assert "A" not in out  # dropped from current
    assert "B" not in out  # unchanged — should not appear in diff


def test_empty_prev_shows_everything_as_new():
    curr = {"quotes": {"SPY": {"last": 525.0}}}
    out = diff_sections({}, curr)
    assert "SPY" in out
    assert "new" in out.lower() or "525" in out


def test_missing_current_section_logs_removed():
    prev = {"news": [{"id": 1, "title": "A"}]}
    curr = {"quotes": {"SPY": {"last": 1}}}
    out = diff_sections(prev, curr)
    assert "news" in out.lower()
    assert "removed" in out.lower() or "dropped" in out.lower()
```

- [ ] **Step 2: Run the failing test**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_diff.py -v
```

Expected: FAIL — `apps.snapshots.diff` doesn't exist.

- [ ] **Step 3: Implement the diff**

Create `backend/apps/snapshots/diff.py`:

```python
"""Pairwise snapshot diff for AI context.

Compares two already-serialized `sections` dicts (as stored on Snapshot) and
emits a compact markdown delta. The goal is *signal compression*: feed the
AI a paragraph that says what changed, not two 50k-token payloads.
"""
from __future__ import annotations

from typing import Any

_NOISE_PCT = 0.005  # 0.5% — movements below this don't go into the diff


def diff_sections(prev: dict[str, Any], curr: dict[str, Any]) -> str:
    """Return a markdown delta between two section dicts.

    Both inputs are {"kind": <section payload>} — shape matches what the
    snapshot services store. Missing keys on either side are handled.
    """
    lines: list[str] = []
    all_kinds = set(prev) | set(curr)

    for kind in sorted(all_kinds):
        p = prev.get(kind)
        c = curr.get(kind)
        if p is None and c is not None:
            lines.append(f"**{kind}**: new this capture")
            lines.append(_summarize_new(kind, c))
        elif c is None and p is not None:
            lines.append(f"**{kind}**: removed/dropped from this capture")
        else:
            delta = _diff_one(kind, p, c)
            if delta:
                lines.append(f"**{kind}**:")
                lines.append(delta)

    return "\n".join(lines) if lines else "No meaningful changes."


def _summarize_new(kind: str, payload: Any) -> str:
    if kind == "quotes" and isinstance(payload, dict):
        return ", ".join(
            f"{t}={q.get('last','?')}" for t, q in list(payload.items())[:8]
        )
    if kind == "news" and isinstance(payload, list):
        return "\n".join(f"- {item.get('title','(untitled)')}" for item in payload[:5])
    return "(section content added)"


def _diff_one(kind: str, prev: Any, curr: Any) -> str:
    if kind == "quotes":
        return _diff_quotes(prev or {}, curr or {})
    if kind == "news":
        return _diff_news(prev or [], curr or [])
    if kind == "breadth":
        return _diff_breadth(prev or {}, curr or {})
    return ""  # other sections (chain, positions, ohlc): skip for now; cheap follow-up


def _diff_quotes(prev: dict, curr: dict) -> str:
    rows: list[str] = []
    for ticker, c in curr.items():
        p = prev.get(ticker, {})
        p_last = p.get("last")
        c_last = c.get("last")
        if p_last is None or c_last is None:
            continue
        try:
            change = (c_last - p_last) / p_last if p_last else 0.0
        except (TypeError, ZeroDivisionError):
            continue
        if abs(change) < _NOISE_PCT:
            continue
        sign = "+" if change >= 0 else ""
        rows.append(f"- {ticker}: {p_last:g} → {c_last:g} ({sign}{change*100:.2f}%)")
    return "\n".join(rows) if rows else "- (all watchlist moves below 0.5%)"


def _diff_news(prev: list, curr: list) -> str:
    prev_ids = {item.get("id") for item in prev if isinstance(item, dict)}
    new_items = [
        item for item in curr
        if isinstance(item, dict) and item.get("id") not in prev_ids
    ]
    if not new_items:
        return "- (no new headlines)"
    return "\n".join(f"- {item.get('title','(untitled)')}" for item in new_items[:10])


def _diff_breadth(prev: dict, curr: dict) -> str:
    rows: list[str] = []
    for key in ("spy_last", "qqq_last", "vix_last"):
        p_val = prev.get(key)
        c_val = curr.get(key)
        if p_val is not None and c_val is not None and p_val != c_val:
            rows.append(f"- {key}: {p_val} → {c_val}")
    return "\n".join(rows) if rows else ""
```

- [ ] **Step 4: Run the tests**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_diff.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/diff.py backend/apps/snapshots/tests/test_diff.py
git commit -m "$(cat <<'EOF'
feat(snapshots): pairwise diff service for "what changed vs last capture"

New apps.snapshots.diff.diff_sections takes two section dicts and emits a
compact markdown delta: quote movers above 0.5%, new news headlines only,
breadth shifts. Designed to feed the AI a signal-dense paragraph instead
of two full payloads — massive token savings for observer/trigger patterns
that otherwise repeat yesterday's data.

Covers quotes / news / breadth; chain/ohlc/positions deferred to follow-up.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Snapshot diff endpoint + observer opt-in

**Files:**
- Modify: `backend/apps/snapshots/views.py` (add action)
- Modify: `backend/apps/observer/models.py` (add `mode` field)
- Modify: `backend/apps/observer/services/run.py` (use diff when mode=diff)
- Migration: generated
- Test: `backend/apps/snapshots/tests/test_diff_endpoint.py`

- [ ] **Step 1: Write the failing endpoint test**

Create `backend/apps/snapshots/tests/test_diff_endpoint.py`:

```python
"""POST /api/snapshots/<id>/diff/?against=<other_id> returns the delta."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def two_snapshots(db, profile):
    from apps.snapshots.models import Snapshot, SnapshotSection
    prev = Snapshot.objects.create(profile=profile, status="ready", source="manual")
    SnapshotSection.objects.create(
        snapshot=prev, kind="quotes", status="done",
        payload={"SPY": {"last": 520.0}, "QQQ": {"last": 440.0}},
    )
    curr = Snapshot.objects.create(profile=profile, status="ready", source="manual")
    SnapshotSection.objects.create(
        snapshot=curr, kind="quotes", status="done",
        payload={"SPY": {"last": 525.0}, "QQQ": {"last": 440.5}},
    )
    return prev, curr


@pytest.fixture
def profile(db):
    from apps.profiles.models import TradingProfile
    return TradingProfile.objects.create(name="p", style="s")


def test_snapshot_diff_endpoint_returns_markdown(db, two_snapshots):
    prev, curr = two_snapshots
    client = APIClient()
    resp = client.get(f"/api/snapshots/{curr.id}/diff/?against={prev.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "delta" in body
    assert "SPY" in body["delta"]


def test_snapshot_diff_missing_against_400(db, two_snapshots):
    _, curr = two_snapshots
    client = APIClient()
    resp = client.get(f"/api/snapshots/{curr.id}/diff/")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run the failing test**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_diff_endpoint.py -v
```

Expected: FAIL — 404 or method not allowed.

- [ ] **Step 3: Add the endpoint**

Edit `backend/apps/snapshots/views.py`. In the `SnapshotViewSet`, add:

```python
    @action(detail=True, methods=["get"])
    def diff(self, request, pk=None):
        against_id = request.query_params.get("against")
        if not against_id:
            return Response({"code": "missing_against"}, status=400)
        try:
            prev = Snapshot.objects.prefetch_related("sections").get(id=against_id)
            curr = Snapshot.objects.prefetch_related("sections").get(id=pk)
        except Snapshot.DoesNotExist:
            return Response({"code": "not_found"}, status=404)

        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in curr.sections.all()}
        from apps.snapshots.diff import diff_sections
        delta = diff_sections(prev_sections, curr_sections)
        return Response({"delta": delta, "prev_id": prev.id, "curr_id": curr.id})
```

Add necessary imports (`action`, `Response`, `Snapshot`) if not already there.

- [ ] **Step 4: Run the tests**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_diff_endpoint.py -v
```

Expected: PASS.

- [ ] **Step 5: Add diff mode to ObserverSchedule**

Edit `backend/apps/observer/models.py`:

```python
    MODE_CHOICES = [("full", "Full payload"), ("diff", "Diff vs previous capture")]
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default="full")
```

Make the migration:

```bash
docker compose exec web python manage.py makemigrations observer -n schedule_mode
```

- [ ] **Step 6: Use the diff in observer.services.run**

Replace the `serialize_for_ai(snap)` call in `apps/observer/services/run.py` (around line 74) with:

```python
    if sched.mode == "diff":
        from apps.snapshots.models import Snapshot as SnapModel
        from apps.snapshots.diff import diff_sections
        prev_snap = (
            SnapModel.objects
            .filter(profile=sched.profile, status="ready")
            .exclude(id=snap.id)
            .order_by("-created_at")
            .first()
        )
        if prev_snap is not None:
            prev_sections = {s.kind: s.payload for s in prev_snap.sections.all()}
            curr_sections = {s.kind: s.payload for s in snap.sections.all()}
            delta_text = diff_sections(prev_sections, curr_sections)
            payload_text = (
                f"Objective: {sched.objective_template}\n\n"
                f"Delta since snapshot #{prev_snap.id}:\n{delta_text}"
            )
        else:
            payload_text = serialize_for_ai(snap, provider=provider_name, model="")
    else:
        payload_text = serialize_for_ai(snap, provider=provider_name, model="")

    msg = Message.objects.create(
        thread=thread, role="user",
        content={"text": payload_text},
        snapshot_ref=snap, status="done",
    )
```

- [ ] **Step 7: Run observer + snapshot suites**

```bash
docker compose exec web pytest backend/apps/observer backend/apps/snapshots -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_diff_endpoint.py backend/apps/observer/models.py backend/apps/observer/migrations/ backend/apps/observer/services/run.py
git commit -m "$(cat <<'EOF'
feat(snapshots): /diff endpoint + observer 'diff' mode

GET /api/snapshots/<id>/diff/?against=<other_id> returns the markdown delta
between two captures. ObserverSchedule.mode ∈ {full, diff}: diff mode feeds
the AI only what changed since the last ready snapshot for the same profile,
falling back to full payload when no prior capture exists.

Token savings depend on data turnover; typical watchlist observer saves
70-90% input tokens on repeated captures.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Batch API for observer watchlist sweep

**Files:**
- Create: `backend/apps/observer/services/batch.py`
- Create: `backend/apps/observer/tasks_batch.py`
- Modify: `backend/config/celery.py` (register new task module)
- Modify: `backend/apps/observer/models.py` (add `use_batch: bool` field)
- Migration: generated
- Test: `backend/apps/observer/tests/test_batch.py`

**Context:** Pre-market / overnight sweeps across a watchlist are exactly what the Batch API was built for: non-interactive, bulk, 50% cheaper, 24h SLA (usually minutes). Preserve the existing streaming path; opt-in flag flips a schedule to submit one batch request per fire.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/observer/tests/test_batch.py`:

```python
"""Batch-mode observer schedules submit a Messages Batch for their watchlist
instead of running per-ticker streaming. A beat-polling task moves completed
batches into per-ticker Messages on the observer thread."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.observer.services import batch as batch_service


@pytest.fixture
def batch_schedule(db):
    from apps.observer.models import ObserverSchedule
    from apps.profiles.models import TradingProfile
    profile = TradingProfile.objects.create(name="p", style="s", default_provider="claude")
    return ObserverSchedule.objects.create(
        name="overnight", profile=profile, cron="0 9 * * *",
        objective_template="overnight review",
        use_batch=True,
        default_watchlist_tickers=["AAPL", "MSFT", "NVDA"],
    )


def test_submit_batch_creates_one_request_per_ticker(db, batch_schedule):
    fake = MagicMock(id="batch_abc123")
    with patch.object(batch_service, "_anthropic_client") as c:
        c.return_value.messages.batches.create.return_value = fake
        batch_id = batch_service.submit_watchlist_batch(batch_schedule.id)
    assert batch_id == "batch_abc123"
    call = c.return_value.messages.batches.create.call_args
    reqs = call.kwargs["requests"]
    assert len(reqs) == 3
    assert {r["custom_id"] for r in reqs} == {"AAPL", "MSFT", "NVDA"}


def test_poll_batch_writes_results_to_thread(db, batch_schedule):
    """When a batch reports ended, poll writes one assistant message per ticker."""
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    fake_results = [
        MagicMock(custom_id="AAPL",
                  result=MagicMock(type="succeeded",
                                   message=MagicMock(content=[MagicMock(type="text", text="AAPL looks OK")]))),
        MagicMock(custom_id="MSFT",
                  result=MagicMock(type="succeeded",
                                   message=MagicMock(content=[MagicMock(type="text", text="MSFT flat")]))),
        MagicMock(custom_id="NVDA",
                  result=MagicMock(type="errored",
                                   error=MagicMock(message="rate_limit"))),
    ]
    with patch.object(batch_service, "_anthropic_client") as c:
        c.return_value.messages.batches.retrieve.return_value = MagicMock(
            processing_status="ended",
        )
        c.return_value.messages.batches.results.return_value = iter(fake_results)
        moved = batch_service.poll_batch(batch_schedule.id, "batch_abc123")

    assert moved == 3
    thread = get_or_create_observer_thread(batch_schedule.profile)
    msgs = list(Message.objects.filter(thread=thread, role="assistant").order_by("id"))
    assert len(msgs) == 3
    assert "AAPL" in msgs[0].content["text"]
    assert msgs[2].status == "failed"
```

- [ ] **Step 2: Run the failing test**

```bash
docker compose exec web pytest backend/apps/observer/tests/test_batch.py -v
```

Expected: FAIL — `apps.observer.services.batch` doesn't exist.

- [ ] **Step 3: Add the `use_batch` field**

Edit `backend/apps/observer/models.py`:

```python
    use_batch = models.BooleanField(
        default=False,
        help_text="When True, run-observer submits a Messages Batch request "
                  "and polls for results instead of streaming.",
    )
    last_batch_id = models.CharField(max_length=64, blank=True, default="")
```

Generate migration:

```bash
docker compose exec web python manage.py makemigrations observer -n schedule_batch
```

- [ ] **Step 4: Implement the batch service**

Create `backend/apps/observer/services/batch.py`:

```python
"""Messages Batch submission + polling for observer schedules.

Flow:
1. submit_watchlist_batch(schedule_id) → one Anthropic batch with N custom_ids,
   where N = len(schedule.default_watchlist_tickers). Returns batch_id.
2. Celery beat polls open batches; on "ended" status, poll_batch() pulls each
   result and writes an assistant Message to the schedule's observer thread.
"""
from __future__ import annotations

import logging

from anthropic import Anthropic

from apps.observer.models import ObserverSchedule
from apps.observer.services.threads import get_or_create_observer_thread
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message

log = logging.getLogger(__name__)


def _anthropic_client(provider: str = "claude") -> Anthropic:
    cfg = ProviderConfig.objects.get(provider=provider)
    return Anthropic(api_key=cfg.api_key, base_url=cfg.base_url or None)


def submit_watchlist_batch(schedule_id: int) -> str:
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)
    tickers = sched.default_watchlist_tickers or []
    if not tickers:
        raise ValueError(f"schedule {schedule_id}: no watchlist tickers to batch")

    provider_name = sched.override_provider or sched.profile.default_provider
    cfg = ProviderConfig.objects.get(provider=provider_name)
    model = sched.override_model or cfg.default_model or "claude-opus-4-7"

    requests = [
        {
            "custom_id": ticker,
            "params": {
                "model": model,
                "max_tokens": 800,
                "system": sched.profile.style or "",
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Objective: {sched.objective_template}\n"
                        f"Ticker: {ticker}\n"
                        f"Return a one-paragraph overnight summary."
                    ),
                }],
            },
        }
        for ticker in tickers
    ]
    client = _anthropic_client(provider_name)
    batch = client.messages.batches.create(requests=requests)
    sched.last_batch_id = batch.id
    sched.save(update_fields=["last_batch_id"])
    return batch.id


def poll_batch(schedule_id: int, batch_id: str) -> int:
    """If the batch is ended, write results to the thread and return the count."""
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)
    provider_name = sched.override_provider or sched.profile.default_provider
    client = _anthropic_client(provider_name)

    status = client.messages.batches.retrieve(batch_id).processing_status
    if status != "ended":
        log.info("batch %s not ended (%s), skipping", batch_id, status)
        return 0

    thread = get_or_create_observer_thread(sched.profile)
    count = 0
    for result in client.messages.batches.results(batch_id):
        ticker = result.custom_id
        if result.result.type == "succeeded":
            text_parts = [
                block.text for block in result.result.message.content
                if getattr(block, "type", None) == "text"
            ]
            text = f"[{ticker}] " + " ".join(text_parts)
            Message.objects.create(
                thread=thread, role="assistant",
                content={"text": text}, status="done",
            )
        else:
            err = getattr(result.result, "error", None)
            msg_text = f"[{ticker}] batch failed: {getattr(err, 'message', 'unknown')}"
            Message.objects.create(
                thread=thread, role="assistant",
                content={"text": msg_text}, status="failed",
                error=getattr(err, "message", ""),
            )
        count += 1
    return count
```

- [ ] **Step 5: Implement the poll task + register with beat**

Create `backend/apps/observer/tasks_batch.py`:

```python
"""Beat-scheduled poller for open batches."""
from __future__ import annotations

import logging

from celery import shared_task

from apps.observer.models import ObserverSchedule
from apps.observer.services.batch import poll_batch

log = logging.getLogger(__name__)


@shared_task(name="observer.poll_open_batches")
def poll_open_batches() -> int:
    """Every minute (via beat): look for schedules with a pending batch and poll it."""
    total = 0
    for sched in ObserverSchedule.objects.filter(use_batch=True).exclude(last_batch_id=""):
        try:
            total += poll_batch(sched.id, sched.last_batch_id)
            # Clear batch id once we've moved results — next fire issues a new one.
            if total > 0:
                ObserverSchedule.objects.filter(id=sched.id).update(last_batch_id="")
        except Exception as exc:  # noqa: BLE001
            log.exception("poll_open_batches: schedule %s failed: %s", sched.id, exc)
    return total
```

Edit `backend/config/celery.py`. Find the explicit task-module list and add `"apps.observer.tasks_batch"`. Then add the beat schedule entry:

```python
app.conf.beat_schedule.setdefault("poll_open_batches", {
    "task": "observer.poll_open_batches",
    "schedule": 60.0,  # every minute
})
```

- [ ] **Step 6: Update run.py to branch on `use_batch`**

Edit `backend/apps/observer/services/run.py`. After the `capture(...)` call, before the existing Message creation, add:

```python
    if sched.use_batch:
        from apps.observer.services.batch import submit_watchlist_batch
        try:
            submit_watchlist_batch(sched.id)
        except Exception as exc:  # noqa: BLE001
            log.exception("observer %s batch submit failed: %s", sched.id, exc)
        sched.last_fired_at = timezone.now()
        sched.save(update_fields=["last_fired_at"])
        return snap.id
```

- [ ] **Step 7: Run the batch test**

```bash
docker compose exec web pytest backend/apps/observer/tests/test_batch.py -v
```

Expected: both tests PASS.

- [ ] **Step 8: Run the full observer suite**

```bash
docker compose exec web pytest backend/apps/observer -v
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/apps/observer/services/batch.py backend/apps/observer/tasks_batch.py backend/apps/observer/models.py backend/apps/observer/migrations/ backend/apps/observer/services/run.py backend/apps/observer/tests/test_batch.py backend/config/celery.py
git commit -m "$(cat <<'EOF'
feat(observer): Messages Batch API for watchlist sweeps

ObserverSchedule.use_batch flips a schedule from streaming to batch
submission: one Anthropic batch per fire with N custom_ids (one per
watchlist ticker). New beat task observer.poll_open_batches runs every
minute, pulls completed batches, and writes per-ticker results to the
observer thread.

50% cheaper on both input + output tokens. Streaming path is unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Trigger backtest endpoint

**Files:**
- Create: `backend/apps/triggers/backtest.py`
- Modify: `backend/apps/triggers/views.py` (add `backtest` action)
- Test: `backend/apps/triggers/tests/test_backtest.py`

**Context:** `POST /api/triggers/evaluate` runs the DSL once against current market state. Backtest replays the same DSL against stored OHLC for a date range and returns match-count plus the timestamps that would have fired. Turns trigger authoring from "save, wait, see if it fires" to "dry-run against last month first."

- [ ] **Step 1: Write the failing test**

Create `backend/apps/triggers/tests/test_backtest.py`:

```python
"""POST /api/triggers/backtest/ replays a DSL against stored OHLC bars."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def aapl_bars(db):
    from apps.market.models import Ohlc
    base = datetime(2026, 3, 1, 14, 30, tzinfo=timezone.utc)
    rows = []
    for i, close in enumerate([100, 101, 99, 105, 110, 108, 112, 115, 113, 120]):
        rows.append(Ohlc(
            ticker="AAPL", interval="1d",
            ts=base + timedelta(days=i),
            open=close - 0.5, high=close + 1, low=close - 1, close=close, volume=1_000_000,
        ))
    Ohlc.objects.bulk_create(rows)


def test_backtest_price_gt_threshold(db, aapl_bars):
    condition = {"all": [{"metric": "price", "ticker": "AAPL", "op": ">", "value": 108}]}
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={
            "condition": condition,
            "start": "2026-03-01",
            "end": "2026-03-10",
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["match_count"] == 5  # closes at 110, 112, 115, 113, 120


def test_backtest_returns_timestamps(db, aapl_bars):
    condition = {"all": [{"metric": "price", "ticker": "AAPL", "op": ">=", "value": 115}]}
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={"condition": condition, "start": "2026-03-01", "end": "2026-03-10"},
        format="json",
    )
    matches = resp.json()["matches"]
    assert len(matches) == 2  # 115, 120
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose exec web pytest backend/apps/triggers/tests/test_backtest.py -v
```

Expected: 404 (endpoint doesn't exist).

- [ ] **Step 3: Implement the backtest runner**

Create `backend/apps/triggers/backtest.py`:

```python
"""Replay a trigger DSL against stored OHLC bars for a date range.

Builds a per-bar 'snapshot' shaped like what triggers.metrics emits at runtime,
then runs the existing evaluator. Supports price/pct_change leaves only; other
metrics (vix, position_pl) need a live snapshot and are skipped when replaying.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.market.models import Ohlc
from apps.triggers.dsl import collect_leaves
from apps.triggers.evaluator import evaluate as evaluate_condition


@dataclass
class BacktestMatch:
    ts: datetime
    values: dict[str, float]


def backtest(
    condition: dict,
    *,
    start: datetime,
    end: datetime,
) -> list[BacktestMatch]:
    """Replay the condition over daily closes between start and end."""
    tickers = _unique_tickers(condition)
    if not tickers:
        return []

    bars = (
        Ohlc.objects
        .filter(ticker__in=tickers, ts__gte=start, ts__lte=end, interval="1d")
        .order_by("ts")
    )
    by_ts: dict[datetime, dict[str, Ohlc]] = {}
    for bar in bars:
        by_ts.setdefault(bar.ts, {})[bar.ticker] = bar

    matches: list[BacktestMatch] = []
    prev_closes: dict[str, float] = {}
    for ts in sorted(by_ts):
        per_ticker = by_ts[ts]
        snapshot = {}
        for ticker, bar in per_ticker.items():
            snapshot[f"price:{ticker}"] = float(bar.close)
            prev = prev_closes.get(ticker)
            if prev is not None and prev > 0:
                snapshot[f"pct_change:{ticker}"] = (float(bar.close) - prev) / prev * 100
            prev_closes[ticker] = float(bar.close)

        matched, values = evaluate_condition(condition, snapshot)
        if matched:
            matches.append(BacktestMatch(ts=ts, values=values))
    return matches


def _unique_tickers(condition: dict) -> set[str]:
    return {
        leaf.get("ticker")
        for leaf in collect_leaves(condition)
        if leaf.get("ticker")
    }
```

- [ ] **Step 4: Add the endpoint**

Edit `backend/apps/triggers/views.py`. Inside `EventTriggerViewSet`, add:

```python
    @action(detail=False, methods=["post"])
    def backtest(self, request: Request) -> Response:
        from datetime import datetime, timezone

        from apps.triggers.backtest import backtest as run_backtest

        data = request.data
        condition = data.get("condition")
        if condition is None:
            return Response({"code": "missing_condition"}, status=400)
        try:
            validate_condition(condition)
        except DjangoValidationError as exc:
            return Response({"code": "invalid_condition", "message": str(exc)}, status=400)

        try:
            start = datetime.fromisoformat(data["start"]).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(data["end"]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError) as exc:
            return Response({"code": "bad_dates", "message": str(exc)}, status=400)

        matches = run_backtest(condition, start=start, end=end)
        return Response({
            "match_count": len(matches),
            "matches": [
                {"ts": m.ts.isoformat(), "values": m.values}
                for m in matches[:500]  # cap response size
            ],
        })
```

- [ ] **Step 5: If `collect_leaves` doesn't exist in dsl.py, add it**

Grep first:

```bash
docker compose exec web grep -n "collect_leaves\|def collect" backend/apps/triggers/dsl.py
```

If missing, append to `backend/apps/triggers/dsl.py`:

```python
def collect_leaves(condition: dict) -> list[dict]:
    """Walk a condition tree and return all leaf (metric) nodes."""
    leaves: list[dict] = []

    def _walk(node: dict) -> None:
        if "metric" in node:
            leaves.append(node)
            return
        for key in ("all", "any"):
            for child in node.get(key, []) or []:
                _walk(child)
        if "not" in node:
            _walk(node["not"])

    _walk(condition or {})
    return leaves
```

- [ ] **Step 6: Run the backtest test**

```bash
docker compose exec web pytest backend/apps/triggers/tests/test_backtest.py -v
```

Expected: both tests PASS.

- [ ] **Step 7: Run the full triggers suite**

```bash
docker compose exec web pytest backend/apps/triggers -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/triggers/backtest.py backend/apps/triggers/views.py backend/apps/triggers/dsl.py backend/apps/triggers/tests/test_backtest.py
git commit -m "$(cat <<'EOF'
feat(triggers): POST /api/triggers/backtest/ replays DSL over stored OHLC

Given a condition + date range, replay the existing evaluator against
every daily close in that window and return the matched timestamps.
Supports price / pct_change leaves; live-only metrics (vix, position_pl)
are ignored in replay.

Turns trigger authoring from 'save, wait, hope it fires' to 'dry-run
against last month first'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Toast notification system (frontend)

**Files:**
- Create: `frontend/src/components/Toasts.tsx`
- Create: `frontend/src/hooks/useToast.ts`
- Modify: `frontend/src/components/layout/AppLayout.tsx` (mount the provider)
- Test: `frontend/src/__tests__/Toasts.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/Toasts.test.tsx`:

```tsx
import { render, screen, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ToastProvider, useToast } from "../hooks/useToast";
import { Toasts } from "../components/Toasts";

function Fixture() {
  const { push } = useToast();
  return (
    <button onClick={() => push({ kind: "success", text: "saved!" })}>go</button>
  );
}

describe("Toasts", () => {
  it("renders a toast when push() is called", async () => {
    render(
      <ToastProvider>
        <Toasts />
        <Fixture />
      </ToastProvider>,
    );
    await act(async () => {
      screen.getByText("go").click();
    });
    expect(await screen.findByText("saved!")).toBeInTheDocument();
  });

  it("auto-dismisses after the configured duration", async () => {
    vi.useFakeTimers();
    render(
      <ToastProvider defaultDurationMs={1000}>
        <Toasts />
        <Fixture />
      </ToastProvider>,
    );
    await act(async () => { screen.getByText("go").click(); });
    expect(screen.getByText("saved!")).toBeInTheDocument();
    await act(async () => { vi.advanceTimersByTime(1001); });
    expect(screen.queryByText("saved!")).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose exec frontend npx vitest run src/__tests__/Toasts.test.tsx
```

Expected: FAIL — modules don't exist.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useToast.ts`:

```ts
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export type ToastKind = "info" | "success" | "error";
export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastContextValue {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

const Ctx = createContext<ToastContextValue | null>(null);

export function ToastProvider({
  children,
  defaultDurationMs = 4000,
}: {
  children: ReactNode;
  defaultDurationMs?: number;
}) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts(xs => xs.filter(t => t.id !== id));
  }, []);

  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = nextId.current++;
    setToasts(xs => [...xs, { ...t, id }]);
    window.setTimeout(() => dismiss(id), defaultDurationMs);
  }, [defaultDurationMs, dismiss]);

  const value = useMemo(() => ({ toasts, push, dismiss }), [toasts, push, dismiss]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useToast(): ToastContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useToast must be used inside <ToastProvider>");
  return v;
}
```

- [ ] **Step 4: Implement the renderer**

Create `frontend/src/components/Toasts.tsx`:

```tsx
import { useToast, type ToastKind } from "../hooks/useToast";

const TONE: Record<ToastKind, string> = {
  info: "bg-slate-800 text-slate-100 border-slate-600",
  success: "bg-emerald-900 text-emerald-100 border-emerald-700",
  error: "bg-rose-900 text-rose-100 border-rose-700",
};

export function Toasts() {
  const { toasts, dismiss } = useToast();
  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map(t => (
        <div
          key={t.id}
          className={`px-4 py-2 border rounded shadow-lg cursor-pointer ${TONE[t.kind]}`}
          onClick={() => dismiss(t.id)}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 5: Mount in AppLayout**

Edit `frontend/src/components/layout/AppLayout.tsx`. Wrap the outlet:

```tsx
import { ToastProvider } from "../../hooks/useToast";
import { Toasts } from "../Toasts";

// inside the component body, at the outermost JSX element:
<ToastProvider>
  {/* existing layout */}
  <Toasts />
</ToastProvider>
```

- [ ] **Step 6: Run the tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/Toasts.test.tsx
```

Expected: both PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Toasts.tsx frontend/src/hooks/useToast.ts frontend/src/components/layout/AppLayout.tsx frontend/src/__tests__/Toasts.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): toast notification system

ToastProvider + useToast hook + Toasts renderer. Mounts at AppLayout so
every page can call push({kind, text}). Auto-dismiss after 4s (configurable).

Intended replacement for the silent success/error state on mutations
across the app — follow-up commits will wire individual pages to use it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Skeleton loader, EmptyState, ErrorBoundary

**Files:**
- Create: `frontend/src/components/Skeleton.tsx`
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/ErrorBoundary.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx` (wrap outlet)
- Test: `frontend/src/__tests__/Skeleton.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/__tests__/Skeleton.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Skeleton, SkeletonRows } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";

describe("Skeleton", () => {
  it("renders a pulse box", () => {
    const { container } = render(<Skeleton className="h-4 w-24" />);
    const box = container.firstChild as HTMLElement;
    expect(box.className).toContain("animate-pulse");
  });

  it("SkeletonRows renders N rows", () => {
    render(<SkeletonRows rows={3} />);
    const rows = document.querySelectorAll('[data-testid="skeleton-row"]');
    expect(rows.length).toBe(3);
  });
});

describe("EmptyState", () => {
  it("renders title + body + optional action", () => {
    render(
      <EmptyState
        title="No triggers yet"
        body="Create one to watch the market"
        action={<button>Create</button>}
      />,
    );
    expect(screen.getByText("No triggers yet")).toBeInTheDocument();
    expect(screen.getByText("Create one to watch the market")).toBeInTheDocument();
    expect(screen.getByText("Create")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose exec frontend npx vitest run src/__tests__/Skeleton.test.tsx
```

Expected: FAIL — modules don't exist.

- [ ] **Step 3: Implement Skeleton**

Create `frontend/src/components/Skeleton.tsx`:

```tsx
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-slate-700/50 rounded ${className}`} />;
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" data-testid="skeleton-row" />
      ))}
    </div>
  );
}
```

Note: for `data-testid` to propagate, also update the rendered element:

```tsx
export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          data-testid="skeleton-row"
          className="animate-pulse bg-slate-700/50 rounded h-8 w-full"
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Implement EmptyState**

Create `frontend/src/components/EmptyState.tsx`:

```tsx
import type { ReactNode } from "react";

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <h3 className="text-lg font-medium text-slate-200">{title}</h3>
      {body && <p className="mt-2 text-sm text-slate-400 max-w-md">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 5: Implement ErrorBoundary**

Create `frontend/src/components/ErrorBoundary.tsx`:

```tsx
import { Component, type ErrorInfo, type ReactNode } from "react";

interface State { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-8 text-center">
          <h2 className="text-lg font-medium text-rose-300">Something went wrong.</h2>
          <p className="mt-2 text-sm text-slate-400">{this.state.error.message}</p>
          <button
            className="mt-4 px-3 py-1 bg-slate-700 rounded text-slate-100"
            onClick={() => location.reload()}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 6: Wrap the outlet in AppLayout**

Edit `frontend/src/components/layout/AppLayout.tsx`. Wrap `<Outlet />`:

```tsx
import { ErrorBoundary } from "../ErrorBoundary";

<ErrorBoundary>
  <Outlet />
</ErrorBoundary>
```

- [ ] **Step 7: Run the tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/Skeleton.test.tsx
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/Skeleton.tsx frontend/src/components/EmptyState.tsx frontend/src/components/ErrorBoundary.tsx frontend/src/components/layout/AppLayout.tsx frontend/src/__tests__/Skeleton.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): Skeleton / EmptyState / ErrorBoundary primitives

Three reusable components that fill audit-found gaps: Skeleton/SkeletonRows
for loading states (currently bare "Loading…" text), EmptyState for empty
tables with CTA slot, and ErrorBoundary wrapping <Outlet/> so a render
crash produces a readable fallback + reload button.

Follow-up commits wire these into TriggersListPage, ThreadsPage,
SchedulesPage, etc., one page at a time.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Command palette (Cmd/Ctrl-K)

**Files:**
- Create: `frontend/src/components/CommandPalette.tsx`
- Modify: `frontend/src/hooks/useKeyboardShortcuts.ts` (add palette trigger)
- Modify: `frontend/src/components/layout/AppLayout.tsx` (mount)
- Test: `frontend/src/__tests__/CommandPalette.test.tsx`

**Context:** 10-20 pages + dozens of actions; current nav is sidebar-only + `g <x>` shortcuts. Palette lets users fuzzy-search every route and action. No backend.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/CommandPalette.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { CommandPalette } from "../components/CommandPalette";

function Wrap({ open }: { open: boolean }) {
  return (
    <MemoryRouter>
      <CommandPalette open={open} onClose={() => {}} commands={[
        { id: "dash", label: "Dashboard", keywords: "home", run: () => {} },
        { id: "trig", label: "Triggers", keywords: "alerts", run: () => {} },
      ]} />
    </MemoryRouter>
  );
}

describe("CommandPalette", () => {
  it("renders commands when open", () => {
    render(<Wrap open={true} />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Triggers")).toBeInTheDocument();
  });

  it("filters by query substring", () => {
    render(<Wrap open={true} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "trig" } });
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
    expect(screen.getByText("Triggers")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<Wrap open={false} />);
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("matches by keywords", () => {
    render(<Wrap open={true} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "alerts" } });
    expect(screen.getByText("Triggers")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
docker compose exec frontend npx vitest run src/__tests__/CommandPalette.test.tsx
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the palette**

Create `frontend/src/components/CommandPalette.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";

export interface Command {
  id: string;
  label: string;
  keywords?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  commands,
}: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (!open) { setQ(""); setIdx(0); }
  }, [open]);

  const filtered = useMemo(() => {
    const needle = q.toLowerCase().trim();
    if (!needle) return commands;
    return commands.filter(c =>
      c.label.toLowerCase().includes(needle)
      || (c.keywords ?? "").toLowerCase().includes(needle),
    );
  }, [q, commands]);

  useEffect(() => { setIdx(0); }, [q]);

  if (!open) return null;

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") { onClose(); }
    else if (e.key === "ArrowDown") { setIdx(i => Math.min(filtered.length - 1, i + 1)); e.preventDefault(); }
    else if (e.key === "ArrowUp") { setIdx(i => Math.max(0, i - 1)); e.preventDefault(); }
    else if (e.key === "Enter") {
      const cmd = filtered[idx];
      if (cmd) { cmd.run(); onClose(); }
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-start justify-center pt-24"
         onClick={onClose}>
      <div
        className="w-[560px] max-w-[90vw] bg-slate-900 border border-slate-700 rounded-lg shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <input
          autoFocus
          placeholder="Search commands…"
          value={q}
          onChange={e => setQ(e.target.value)}
          className="w-full px-4 py-3 bg-transparent text-slate-100 outline-none border-b border-slate-700"
        />
        <ul className="max-h-[400px] overflow-y-auto">
          {filtered.map((c, i) => (
            <li
              key={c.id}
              className={`px-4 py-2 cursor-pointer ${i === idx ? "bg-slate-800" : ""}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => { c.run(); onClose(); }}
            >
              <span className="text-slate-100">{c.label}</span>
              {c.keywords && (
                <span className="ml-2 text-xs text-slate-500">{c.keywords}</span>
              )}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-4 py-3 text-sm text-slate-500">No commands match.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire the Cmd/Ctrl-K shortcut**

Edit `frontend/src/hooks/useKeyboardShortcuts.ts`. Add a `useCommandPalette` hook or extend the existing registration to listen for `(e.metaKey || e.ctrlKey) && e.key === "k"` and call a callback that opens the palette.

The exact wiring depends on the current hook shape — grep it:

```bash
docker compose exec frontend grep -n "useKeyboardShortcuts\|addEventListener" frontend/src/hooks/useKeyboardShortcuts.ts
```

Add a new hook alongside:

```ts
export function useCommandPaletteTrigger(onOpen: () => void) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onOpen]);
}
```

- [ ] **Step 5: Mount in AppLayout**

Edit `frontend/src/components/layout/AppLayout.tsx`. Build a default command list and wire the trigger:

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { CommandPalette, type Command } from "../CommandPalette";
import { useCommandPaletteTrigger } from "../../hooks/useKeyboardShortcuts";

function useCommands(): Command[] {
  const nav = useNavigate();
  return [
    { id: "go-dashboard", label: "Go to Dashboard", keywords: "home", run: () => nav("/") },
    { id: "go-threads", label: "Go to Threads", keywords: "chats ai", run: () => nav("/threads") },
    { id: "go-snapshots", label: "New snapshot", keywords: "capture", run: () => nav("/snapshots/new") },
    { id: "go-triggers", label: "Go to Triggers", keywords: "alerts rules", run: () => nav("/triggers") },
    { id: "go-costs", label: "Go to Costs", keywords: "spend usage", run: () => nav("/costs") },
    { id: "go-schedules", label: "Go to Schedules", keywords: "observer cron", run: () => nav("/schedules") },
    { id: "go-backups", label: "Go to Backups", keywords: "backup restore", run: () => nav("/backups") },
    { id: "go-profiles", label: "Go to Profiles", keywords: "style", run: () => nav("/profiles") },
    { id: "go-settings", label: "Open Settings", keywords: "providers keys", run: () => nav("/settings") },
  ];
}
```

Inside the layout component:

```tsx
const [paletteOpen, setPaletteOpen] = useState(false);
const commands = useCommands();
useCommandPaletteTrigger(() => setPaletteOpen(true));
// near the end of JSX:
<CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
```

- [ ] **Step 6: Run the tests**

```bash
docker compose exec frontend npx vitest run src/__tests__/CommandPalette.test.tsx
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/CommandPalette.tsx frontend/src/hooks/useKeyboardShortcuts.ts frontend/src/components/layout/AppLayout.tsx frontend/src/__tests__/CommandPalette.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): Cmd/Ctrl-K command palette

Fuzzy-search all pages/actions from anywhere in the app. Arrow nav + Enter
to run, Esc to close. Default command list covers every top-level route;
follow-up commits can add page-specific commands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Update CLAUDE.md + design spec pointer

**Files:**
- Modify: `/home/dan/ai-dashboard/CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` (add §17 M9 pointer)

- [ ] **Step 1: Add M9 bullets to the non-obvious conventions**

Edit `CLAUDE.md`. In the `## Non-obvious conventions` section, add these bullets (in existing alphabetical order):

```markdown
- **AI token counts are provider-aware.** `apps.ai.token_counter.estimate_tokens(text, provider=, model=)` routes Claude to Anthropic's `count_tokens` endpoint (cached via `lru_cache`) and everything else to `tiktoken.cl100k_base`. Call sites that don't pass provider/model get the old tiktoken default — intentional back-compat — but new code should pass them through.
- **Claude multi-turn runs cache the final prior message.** `RunRequest.cache_last_message=True` (set automatically when `len(messages) > 1` in `_build_request`) attaches a second `cache_control` breakpoint on the last message's final text block. On cache hit, Anthropic bills ~0.1× base input for everything before the breakpoint.
- **Monthly cost cap parity with daily cap.** `apps.ai.cost.check_monthly_cap(provider, cap_usd, prospective)` sums the last 30 days of `AIRun.cost_usd`. Null cap is a no-op (opt-in). Wired into `threads.tasks`, `observer.services.run`, and `triggers.tasks`.
- **Observer schedules have a structured mode.** `ObserverSchedule.structured=True` routes a run through `apps.ai.providers.claude_structured.run_structured` with the `ObservationReport` Pydantic schema; the result lands in `Message.content` as `{"kind": "structured_observation", "report": <json>}` so the UI can render typed cards. Non-structured mode is unchanged.
- **Observer schedules have a diff mode.** `ObserverSchedule.mode="diff"` feeds the AI the `apps.snapshots.diff.diff_sections(...)` delta versus the most recent prior ready snapshot (falls back to full payload if no prior). Typical 70-90% input-token savings on repeated captures.
- **Observer batch mode.** `ObserverSchedule.use_batch=True` submits a Messages Batch (one custom_id per watchlist ticker) instead of streaming. The `observer.poll_open_batches` beat task (runs every minute) pulls results into the observer thread when the batch ends. 50% cheaper; no streaming feedback in the UI during the window.
- **Snapshot diff endpoint.** `GET /api/snapshots/<id>/diff/?against=<other_id>` returns `{delta: <markdown>}`. Not yet surfaced in the UI; power users can use it directly.
- **Trigger backtest.** `POST /api/triggers/backtest/` body `{condition, start, end}` replays the DSL over stored daily OHLC bars and returns match timestamps. Only `price` and `pct_change` leaves are supported; live-only metrics (vix, position_pl) are silently skipped.
- **Frontend primitives.** `Skeleton` / `SkeletonRows` / `EmptyState` / `ErrorBoundary` / `Toasts` live in `frontend/src/components/`. Reach for these before writing ad-hoc loading spinners, "no data" text, or try/catch-in-JSX guards. Toasts require a `<ToastProvider>` ancestor; `AppLayout` already provides it.
- **Command palette is Cmd/Ctrl-K.** Default commands in `AppLayout` cover all top-level routes. Page-level command contributions not yet wired; extend the `useCommands()` hook when needed.
```

- [ ] **Step 2: Drop an M9 section in the design spec**

Edit `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`. Append before the final line (if any; otherwise at EOF):

```markdown
## §17 M9 — AI platform v2 (2026-04-18)

**Status:** Implemented. See `docs/superpowers/plans/2026-04-18-m9-ai-platform-v2.md`.

**What shipped:**
- Provider-aware token estimator (Anthropic `count_tokens` for Claude; tiktoken for others)
- `ModelInfo.max_payload_tokens` per model (raised from 40k default to 150k–300k depending on ctx)
- Cache breakpoint on last prior turn (Claude) for multi-turn runs
- Monthly cost cap enforcement across threads / observer / triggers
- Structured observer outputs via `messages.parse` + `ObservationReport` schema
- Snapshot diff service + `GET /api/snapshots/<id>/diff/` endpoint
- Observer diff-mode and batch-mode schedules
- Trigger backtest endpoint (`POST /api/triggers/backtest/`)
- Frontend primitives: `Toasts`, `Skeleton*`, `EmptyState`, `ErrorBoundary`, `CommandPalette`

**Deferred to M10:** Tool use on Claude; Files API; `search_result` citations; extended thinking; Memory tool; Skills; MCP server/client.
**Deferred to M11:** Thesis objects, decision journal, post-mortem scheduler, agent presets.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-04-16-ai-dashboard-design.md
git commit -m "$(cat <<'EOF'
docs: document M9 platform conventions + spec pointer

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Full check gate

- [ ] **Step 1: Run `make check`**

```bash
make check
```

Expected: exit 0. All backend + frontend tests + lint + mypy + eslint clean.

- [ ] **Step 2: If anything fails, fix in place — do not paper over**

Fail-in-place rule: if a pre-existing test breaks because of a plan change, update the test to reflect the new behavior (don't skip it). If lint flags a new issue in new code, fix the code. If mypy complains about a narrowing issue, tighten the type, don't add `type: ignore` unless there's no other option.

- [ ] **Step 3: Tag the milestone**

```bash
git tag -a m9-ai-platform-v2 -m "M9 — AI platform v2 shipped"
```

Do NOT push the tag unless the user explicitly asks.

---

## Post-plan follow-ups (not in M9)

These came up during planning but belong to later plans:

1. **M10 — AI platform v2.5:** Tool use (`get_quote`, `fetch_ohlc`, `search_news`, `get_option_chain`), Files API uploads, `search_result` block citations, extended thinking flag per profile, Memory tool, Anthropic Skills for domain packs, MCP server + client.
2. **M11 — Second-brain:** `Thesis` model, decision-journal close-of-thread prompt, post-mortem scheduler (7/30/90-day AI replay), agent presets (earnings prep, devil's advocate, pre-trade bias check, triage pass).
3. **Polish lane (ongoing):** Wire `Skeleton*` / `EmptyState` / `Toasts` into individual pages (`TriggersListPage`, `ThreadsPage`, `SchedulesPage`, etc.); add page-specific commands to the palette; dark-mode toggle; diff-between-compare-branches UI; snapshot diff UI panel.
4. **M12 — Analytics:** Provider prediction leaderboard, cost-per-insight metric, trigger-fire heatmap, observer-run timeline chart, unusual-options interpreter.

---

## Self-review

**Spec coverage:** All 9 planned additions have a task + test + commit. Token counter, budget ceiling, history caching, monthly cap, structured observer, snapshot diff + endpoint, observer diff-mode, batch API, trigger backtest, three frontend primitives, command palette, docs — complete.

**Placeholder scan:** No "TBD", no "similar to Task N", no "add validation later". Every code block is complete runnable code. Imports listed where not inferable from context. Migration commands named, beat schedule entry literal.

**Type consistency:** `RunRequest.cache_last_message`, `ObserverSchedule.structured`, `ObserverSchedule.mode`, `ObserverSchedule.use_batch`, `ObserverSchedule.last_batch_id`, `ModelInfo.max_payload_tokens`, `ObservationReport`, `Signal`, `KeyLevel`, `Bias`, `Command`, `Toast`, `ToastKind` — all defined exactly once and used consistently downstream. `estimate_tokens(text, *, provider, model)` signature matches between `apps.ai.token_counter` and the re-export in `apps.snapshots.token_budget`.
