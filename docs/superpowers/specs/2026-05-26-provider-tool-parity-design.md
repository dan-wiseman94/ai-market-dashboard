# Provider tool parity + capability warnings — design

**Date:** 2026-05-26
**Status:** Approved (pending spec review)
**Topic:** Extend tool-calling to the OpenAI / local providers, and surface a visible warning when a profile enables a feature the selected provider cannot do.

## Problem

Local OpenAI-compatible endpoints are *fully supported for the core chat/observation flow* (streaming text, usage, zero-cost accounting — `LocalProvider` is a thin subclass of `OpenAIProvider`). But every M10 feature is Claude-only, and enabling one on a non-Claude profile is a **silent no-op**, not an error:

- `apps/threads/tasks.py:_build_request` gates tools / thinking / memory behind `provider_name == "claude"`.
- `OpenAIProvider.run()` never reads `req.tools`, `req.thinking_budget`, or `req.memory_dir`.

So a user who enables tool use on a local profile gets a plain-text answer with no indication that tools did nothing.

This design closes two gaps:

1. **Tool-calling parity** for OpenAI and local providers (the OpenAI SDK supports function calling; the local endpoint may or may not, hence opt-in).
2. **Visible capability warnings** so that genuinely-unsupported features (thinking, memory) — and tools on an endpoint that doesn't support them — are loud rather than silent.

## Non-goals (YAGNI)

- Thinking / memory / Files API / citations parity on non-Claude providers. These stay Claude-only; we only make their absence *visible*.
- Per-message feature warnings (attached files, news citations). Those are request-construction details, not profile toggles. The pre-existing news-citation silent drop on non-Claude providers stays as-is.
- Warning emission on the observer / trigger (unattended) paths. Tool-support parity *does* extend there automatically because it lives in the shared `_build_request`; only the warning *message* is scoped to the interactive threads path where a user is present to read it.
- Frontend components. The WS `warning` event and the inline `system` message render through existing message plumbing.

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| How to decide whether to send tools to OpenAI/local | `supports_tools` boolean on `ProviderConfig` | Mirrors the existing `supports_vision` field; explicit, no surprise 400s |
| What happens when an unsupported feature is enabled | Warn and continue (degraded) | Least disruptive; makes today's silent no-op loud without blocking the run |
| Where the warning surfaces | Thread `system`/`done` message + WS `warning` event | Reuses the cost-cap-skip precedent; visible inline and in history |
| Where tool serialization lives | `Toolset` owns it (`openai_tools()` alongside `anthropic_tools()`) | One tested place; providers stay thin and forward `req.tools` verbatim |
| `supports_tools` default | `True` | OpenAI proper reliably supports tools; local users whose endpoint doesn't can toggle off. With warn-and-continue, an endpoint that *ignores* tools simply won't call them. |

## Architecture

The streaming loop `drive()` in `apps/threads/tasks.py` is **already provider-agnostic** — it handles `ToolCallEvent` / `ToolResultEvent` / `ThinkingDeltaEvent` regardless of which provider emitted them, persists `ToolCall` rows, and broadcasts WS events. Therefore, making `OpenAIProvider.run()` emit the existing `ToolCallEvent` / `ToolResultEvent` requires **zero changes** to `tasks.py`'s event handling, the WS consumer, or the frontend.

### Components

**1. `apps/ai/tools/__init__.py` — `Toolset.openai_tools()`**

New sibling to `anthropic_tools()`:

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

Tool `name` is preserved across both shapes, so dispatch by name works identically.

**2. `apps/ai/providers/openai.py` — tool loop**

Add a loop mirroring `claude.py:51-148`. Key differences from Claude (OpenAI streaming semantics):

- Pass `tools=req.tools` to `chat.completions.create` only when `req.tools` is non-empty.
- OpenAI streams tool calls as `choice.delta.tool_calls` fragments carrying `index`, `id`, `function.name`, and `function.arguments`. **`arguments` arrives as partial-JSON string chunks across multiple deltas** — accumulate by `index`, then `json.loads` once the stream completes.
- On `finish_reason == "tool_calls"`:
  - For each accumulated call: emit `ToolCallEvent`, dispatch via `default_toolset().run(name, parsed_input)` (late import, same pattern as `claude.py:_resolve_toolset`), emit `ToolResultEvent`.
  - Append the assistant turn with its `tool_calls` array, then one `{"role": "tool", "tool_call_id": id, "content": result_str}` per result.
  - Loop.
- Sum usage across iterations (Claude does the same).
- `LocalProvider` inherits the whole loop unchanged.
- Mock-mode short-circuit stays at the top of `run()` — tools are not exercised under `MOCK_EXTERNAL`.

Malformed tool-argument JSON from the model is dispatched as an error result (`{"ok": False, "error": ...}`) rather than raising, so a single bad call degrades gracefully instead of failing the run.

**3. `apps/secrets/models.py` + migration — `supports_tools`**

```python
supports_tools = models.BooleanField(default=True)
```

Mirrors `supports_vision`. Expose in `ProviderConfigSerializer.Meta.fields`. New Django migration.

**4. `apps/threads/tasks.py:_build_request` — extended gating**

Replace the `provider_name == "claude"`-only tool block:

- **Claude:** unchanged — `default_toolset().anthropic_tools()` when `profile.enable_tools`.
- **OpenAI / local:** `default_toolset().openai_tools()` when `profile.enable_tools AND supports_tools`.
- `thinking_budget` / `memory_dir` remain Claude-only.

`_build_request` needs the resolved `supports_tools` value. **All three callers** (`run_ai_on_message`, observer `services/run.py`, `triggers/tasks.py`) already fetch the `ProviderConfig`; each passes `supports_tools=cfg.supports_tools` so tool parity is uniform across interactive, observer, and trigger runs. The signature default is `supports_tools: bool = False` — a conservative guard so any caller that forgets to wire it through sends *no* tools rather than risking a 400 against a local endpoint, never the reverse.

**5. `apps/ai/capabilities.py` — pure helper (new)**

```python
def unsupported_features(provider_name, profile, *, supports_tools) -> list[str]:
    """Return human-readable names of features enabled on the profile that the
    selected provider cannot honor. Empty list => fully compatible."""
```

Rules:
- `provider_name == "claude"` → always `[]`.
- non-Claude: `enable_thinking` → "extended thinking"; `enable_memory` → "memory"; `enable_tools and not supports_tools` → "tool use".

Pure function, parametrized truth-table tests.

**6. Warning emission in `run_ai_on_message`**

After resolving provider + `ProviderConfig`, call `unsupported_features(...)`. If non-empty:
- Write a `system`/`done` `Message` (reuse the cost-cap-skip message pattern) whose content names the ignored feature(s) and the provider.
- Broadcast a WS `warning` event over `thread.<id>` (`{"event": "warning", "message_id": ..., "text": ...}`).
- **Then continue the run normally** (degraded).

**Dedupe:** skip writing if the thread's most recent `system` message already carries the same warning key, so a long conversation on a mismatched profile doesn't spam identical warnings.

## Data flow

```
user sends message
  → run_ai_on_message
      → resolve provider_name + ProviderConfig (supports_tools)
      → unsupported = unsupported_features(provider_name, profile, supports_tools=...)
      → if unsupported and not duplicate: write system Message + WS "warning"
      → _build_request(..., supports_tools=...)
          → tools = anthropic_tools() | openai_tools() | []   (per provider + gating)
      → provider.run(req)
          → OpenAIProvider: stream text + accumulate tool_call deltas
              → on finish_reason "tool_calls": ToolCallEvent → toolset.run → ToolResultEvent → loop
      → drive() (unchanged) broadcasts text_delta / tool_call / tool_result, persists ToolCall rows
```

## Error handling

- **Endpoint rejects `tools=`** (e.g. local model with no function-calling): the `chat.completions.create` call raises; existing `except Exception` in `run()` yields `ErrorEvent`, surfaced as a failed message. The `supports_tools=False` toggle is the user's lever to avoid this.
- **Endpoint ignores `tools=`**: model returns plain text, `finish_reason != "tool_calls"`, loop exits after one iteration — graceful, no tool calls.
- **Malformed tool-call arguments JSON**: dispatched as an error tool result, conversation continues.
- **Unknown tool name**: already handled by `Toolset.run` → `{"ok": False, "error": "Unknown tool: ..."}`.

## Testing

- `Toolset.openai_tools()` — shape assertion.
- `OpenAIProvider` tool loop — fake `AsyncOpenAI` stream (follow `test_local_provider.py` / `test_openai.py`): tool_call delta accumulation across chunks, `ToolCallEvent` / `ToolResultEvent` emission and order, second iteration after tool result, summed usage across iterations, malformed-arguments degradation.
- `_build_request` gating matrix — claude / openai+supports_tools / openai−supports_tools / local.
- `unsupported_features` — parametrized truth table across providers and flag combinations.
- Warning emission — system `Message` written, WS `warning` broadcast, dedupe suppresses the second identical warning.
- Migration applies cleanly.

## Files touched

| File | Change |
|---|---|
| `apps/ai/tools/__init__.py` | add `Toolset.openai_tools()` |
| `apps/ai/providers/openai.py` | tool loop + tool dispatch + arg accumulation |
| `apps/secrets/models.py` | `supports_tools` field |
| `apps/secrets/migrations/000X_*.py` | new migration |
| `apps/secrets/serializers.py` | expose `supports_tools` |
| `apps/threads/tasks.py` | extend `_build_request` gating; emit warning in `run_ai_on_message` |
| `apps/ai/capabilities.py` | new pure helper |
| `apps/ai/tests/test_*` | provider loop, toolset shape, capabilities, gating tests |
| `apps/threads/tests/test_*` | warning emission + dedupe |
