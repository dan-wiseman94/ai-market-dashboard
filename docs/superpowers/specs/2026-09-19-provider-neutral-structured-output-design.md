# Provider-neutral structured output + model catalog refresh — design

**Date:** 2026-09-19
**Status:** approved in chat, spec for review
**Branch:** `worktree-provider-neutral-structured-output`

## Why

Every self-measurement path in the app — the Prediction Ledger (`AIPrediction`), the
look-ahead-safe eval harness (`EvalRun`), calibration-weighted routing, observer consensus,
and the War Room verdict — runs through one function,
`apps.ai.providers.claude_structured.run_structured`, which wraps Anthropic `messages.parse`.
Nothing that isn't Claude can produce a structured `ObservationReport`, so nothing that isn't
Claude can ever be scored. The question "which provider forms better hypotheses" is therefore
unanswerable inside the harness today.

Separately, `apps/ai/catalog.py` predates every current model. An unknown model id gets a
40k-token snapshot budget (the serializer prunes chain/OHLC first) and is billed at the
provider's priciest catalog row; the Opus 4.8 row is priced 3x high and the three GPT-5 rows
about 4x high against the vendors' current price pages.

## Goals

1. `run_structured` works for `claude`, `openai`, and `local` behind one signature, records
   an `AIRun` under the real provider, and every existing caller resolves its provider the
   same way the streaming path does (override → profile → calibration → first enabled).
2. Consensus becomes real cross-vendor agreement; eval can score any provider; the ledger
   records whichever provider fired.
3. The catalog lists current models with verified prices and windows, corrects the stale rows,
   and the fallback default model is per-provider.

## Non-goals

- Streaming `Provider` classes are untouched.
- The Anthropic Messages Batch path (`observer/services/batch.py`) stays Claude-only; it is
  vendor-specific by nature.
- No `provider` column on `EvalRun` (a model id identifies its vendor); no frontend changes.
- No critic stage, War Room role assignment, or snapshot-as-debate-subject work.
- Local runs remain `$0` in `cost.py`.

## 1. Facade: `apps/ai/structured.py` (new, public)

The only import path for callers outside `apps.ai`.

```python
def run_structured[M: BaseModel](
    *, provider: str, api_key: str, model: str, system: str, user: str,
    output_model: type[M], max_tokens: int = 2048, base_url: str = "",
) -> M
```

- Dispatch: `provider in CLAUDE_FAMILY_PROVIDERS` → `providers.claude_structured.run_structured`;
  `"openai"` and `"local"` → `providers.openai_structured.run_structured` (which receives the
  provider name so it can record the run correctly and pick the local fallback). Any other
  name raises `ValueError`.
- Re-exports `StructuredParseError`, `token_usage_from_anthropic`, `token_usage_from_openai`.

### 1.1 Target resolution

```python
class StructuredTarget(NamedTuple):
    provider: str; model: str; api_key: str; base_url: str
    daily_cap: Decimal; monthly_cap: Decimal | None

def resolve_structured_target(*, profile=None, override_provider="", override_model="") -> StructuredTarget | None
def structured_capable_targets() -> list[StructuredTarget]
def ensure_within_caps(target: StructuredTarget) -> None   # raises CostCapExceededError
```

Precedence for `resolve_structured_target`, mirroring `apps.ai.router`:

1. `override_provider` (+ `override_model` if given, else that config's `default_model`, else
   the catalog default for the provider).
2. `profile.default_provider` / `profile.default_model` the same way.
3. `router._calibration_choice()` when `AI_CALIBRATION_ROUTING_ENABLED`.
4. First enabled `ProviderConfig` by id.

A target is **usable** when its config is enabled and it has a credential: a non-empty
`api_key` for `claude`/`openai`, or a non-empty `base_url` for `local` (key optional). A
config that resolves but is unusable yields `None` — callers already treat `None` as "skip,
never raise". `InvalidToken` on key decryption **propagates** from the single-target resolver;
callers keep their existing handling (the observer records an `undecryptable_key` Message,
the narrative callers skip). `structured_capable_targets()` enumerates every usable enabled
config, skipping undecryptable ones with a warning, exactly as consensus does today.

`ensure_within_caps` wraps the two existing cap checks so callers stop duplicating them.

## 2. Catalog: `apps/ai/catalog.py`

Rows added (prices per 1M tokens, verified 2026-09-19 against the vendors' model pages):

| provider | id | input | cached | output | context | payload budget |
|---|---|---|---|---|---|---|
| claude | `claude-fable-5-1` | 10.00 | 0.25 | 50.00 | 1,000,000 | 150,000 |
| claude | `claude-opus-5` | 5.00 | 0.50 | 25.00 | 1,000,000 | 150,000 |
| claude | `claude-sonnet-5` | 2.00 | 0.20 | 10.00 | 1,000,000 | 150,000 |
| openai | `gpt-6-astra` | 10.00 | 1.00 | 50.00 | 1,050,000 | 300,000 |
| openai | `gpt-5.6-sol` | 4.00 | 0.40 | 20.00 | 1,050,000 | 300,000 |

Rows corrected (ids and payload budgets unchanged so existing configs keep working):

| id | change |
|---|---|
| `claude-opus-4-8` | 15/1.875/75 → **5.00 / 0.50 / 25.00**; context 200k → 1M |
| `claude-sonnet-4-6` | context 200k → 1M (price unchanged) |
| `gpt-5` | 5/0.50/40 → **1.25 / 0.125 / 10.00** |
| `gpt-5-mini` | 0.60/0.06/4.80 → **0.25 / 0.025 / 2.00** |
| `gpt-5-nano` | 0.15/0.015/1.20 → **0.05 / 0.005 / 0.40** |

Constants and helpers:

- `DEFAULT_CLAUDE_MODEL = "claude-opus-5"`, new `DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"`,
  new `default_model_for(provider) -> str`: any name in `CLAUDE_FAMILY_PROVIDERS` →
  `DEFAULT_CLAUDE_MODEL`, `openai` → `DEFAULT_OPENAI_MODEL`, `""` for `local` and unknown
  providers (local models must be configured). Callers that spelled
  `cfg.default_model or DEFAULT_CLAUDE_MODEL` switch to
  `cfg.default_model or default_model_for(provider)`.
- `ceiling_for_provider` is unchanged in behaviour; its result moves to `claude-fable-5-1`
  and `gpt-6-astra`. The two catalog tests pinning ceiling ids are updated.
- `CLAUDE_FAMILY_PROVIDERS` unchanged.

## 3. OpenAI / Local implementation: `apps/ai/providers/openai_structured.py` (new, private)

```python
def run_structured[M: BaseModel](*, provider: str, api_key: str, model: str, system: str, user: str,
                                  output_model: type[M], max_tokens: int = 2048, base_url: str = "") -> M
```

- Client: sync `OpenAI(api_key=api_key or "sk-local-placeholder", base_url=base_url or None,
  **client_kwargs())` — the placeholder mirrors `LocalProvider`, which exists because the SDK
  demands a key at construction.
- Request: `client.chat.completions.parse(model=..., messages=[system?, user],
  response_format=output_model, ...)`. The system message is omitted when `system` is empty.
  Token cap is `max_completion_tokens` for `openai` and `max_tokens` for `local` (older
  OpenAI-compatible servers reject the newer name).
- Result: `choices[0].message`. A non-empty `refusal` or a `None` `parsed` raises
  `StructuredParseError`. The SDK's `LengthFinishReasonError` / `ContentFilterFinishReasonError`
  propagate unchanged; every caller already catches `Exception`.
- **Local fallback (provider == "local" only):** on `openai.BadRequestError` from the strict
  request, retry once with `chat.completions.create(response_format={"type": "json_object"})`,
  the model's JSON schema and the word "JSON" appended to the system prompt, then strip
  Markdown code fences from `message.content` and `output_model.model_validate_json` it. A
  Pydantic `ValidationError` becomes `StructuredParseError`. An `openai` 400 is a real error
  and is not retried.
- Usage: `token_usage_from_openai(usage)` → `TokenUsage(input_tokens=prompt_tokens,
  output_tokens=completion_tokens, cached_tokens=prompt_tokens_details.cached_tokens,
  cache_write_tokens=0)`, the same subset convention the streaming `OpenAIProvider` uses.
  Recorded best-effort via `record_ai_run(provider=provider, ...)` (log-and-continue on
  failure, mirroring the Claude path).
- No `MOCK_EXTERNAL` short-circuit, for parity with the Claude path; tests patch the SDK
  client class (`patch("apps.ai.providers.openai_structured.OpenAI", ...)`).

`StructuredParseError` stays defined in `claude_structured.py`; `openai_structured.py`
imports it from there and the facade re-exports it.

## 4. Caller migration

| file | change |
|---|---|
| `observer/services/run.py` | Drop the `CLAUDE_FAMILY_PROVIDERS` guard and its `unsupported_provider` Message. `model_id = sched.override_model or cfg.default_model or default_model_for(provider_name)`. Pass `provider=provider_name`. Import from the facade. |
| `observer/serializers.py` | `_validate_claude_only_modes` currently rejects both `structured` and `use_batch` on non-Claude schedules. The `structured` half is removed; `use_batch` keeps its Claude-only validation (Messages Batches is Anthropic-specific). |
| `observer/services/consensus.py` | `structured_capable_pairs()` becomes a thin alias of `structured_capable_targets()`; `StructuredPair` aliases `StructuredTarget`; `_STRUCTURED_PROVIDERS` and the "Claude-only today" docstring go. Each take passes `provider=pair.provider`. |
| `observer/services/batch.py` | Import `token_usage_from_anthropic` from the facade. Behaviour unchanged. |
| `analytics/services/aieval.py` | `replay_one(..., provider="claude")`, `evaluate(..., provider="claude")`, `serialize_for_ai(snapshot, provider=provider, model=model)`, cfg lookup on that provider. `preflight_cost_cap(provider)` unchanged in shape. Management command gains `--provider` (default `claude`). Docstring: the look-ahead boundary is provider-independent. |
| `strategy/warroom/services/convene.py` + `tasks.py` | `_claude_cfg()` → `_synth_target()` = `resolve_structured_target()` + `ensure_within_caps`. Error text becomes "no provider for synthesis". |
| `strategy/warroom/services/verdict.py` | `synthesize(..., provider=)`, facade import. |
| `strategy/coverage/services/revise.py` | Resolve via `resolve_structured_target(profile=profile)`; drop the manual cfg/key/cap block; default model per provider. |
| `thesis/services/postmortem.py` | Same; the "provider is not claude — skipping" branch is deleted. |
| `strategy/regime/services/narrative.py`, `book/services/narrative.py` | Same (no profile → global precedence). |

Callers' outward behaviour on "no provider / no key / cap hit / provider error" is unchanged:
skip or record a failed Message, never raise.

## 5. Contracts and docs

- `pyproject.toml` import-linter: add `apps.ai.providers.claude_structured` and
  `apps.ai.providers.openai_structured` to `forbidden_modules`; the comment names
  `apps.ai.structured` as the public surface.
- `CLAUDE.md`: the "thinking/memory/files/citations/structured-output are Claude-only" line
  becomes "thinking/memory/files/citations are Claude-only; structured output has provider
  parity via `apps.ai.structured` (OpenAI strict JSON schema, Local best-effort with a
  `json_object` fallback)". The consensus line drops its Claude-only caveat. The eval line
  notes `--provider`. The catalog line notes per-provider defaults and that Opus 5 /
  GPT-5.6 Sol are the fallbacks.
- Docstrings in `consensus.py`, `aieval.py`, `claude_structured.py` are rewritten to present
  tense with no history.

## 6. Testing

New:

- `ai/tests/test_openai_structured.py` — parse success records an `AIRun` with
  `provider="openai"` and a non-zero cost; `provider="local"` records `$0`; refusal raises
  `StructuredParseError`; `parsed is None` raises; `local` 400 → `json_object` fallback →
  validated result; fallback `ValidationError` → `StructuredParseError`; `openai` 400 is not
  retried; usage mapping incl. `cached_tokens`; empty `system` omits the system message.
- `ai/tests/test_structured_facade.py` — dispatch for `claude`/`anthropic`/`openai`/`local`,
  unknown provider raises; resolver precedence (override > profile > calibration > first
  enabled); `local` usable with base_url and no key; keyless `openai` → `None`;
  `InvalidToken` propagates; `structured_capable_targets` enumerates every usable provider
  and skips undecryptable ones; `default_model_for`.
- `ai/tests/test_structured_schemas_strict.py` — each of the six output models
  (`ObservationReport`, `PostMortemReport`, `CoverageRevisionDraft`, `RegimeNarrative`,
  `BookNarrative`, `WarRoomVerdict`) converts through the OpenAI SDK's strict-schema
  converter without error. Catches Pydantic features strict mode rejects, offline.

Updated:

- `ai/tests/test_catalog*.py` — new ids present, corrected prices, ceilings, defaults.
- `observer/tests/test_consensus_service.py` — "claude family only" → "every usable
  provider"; keyless/disabled cases kept.
- `observer/tests/test_structured_outputs.py` / `test_consensus_observer.py` — an
  `openai`-only schedule in structured mode runs and extracts a prediction with
  `provider="openai"`; no `unsupported_provider` Message.
- `analytics/tests/test_aieval.py` — `provider="openai"` resolves the OpenAI config and
  preflights that provider's caps.
- `strategy/warroom/tests/test_verdict.py`, `strategy/tests/test_task_acks.py` —
  synthesizer works with an OpenAI-only config.
- `coverage/regime/book/postmortem` tests — one case each: an OpenAI-only config now runs.

Gates: `ruff`, `mypy` (zero baseline), `lint-imports`, `deptry`, `semgrep-rules`, `pytest`
run against the worktree through a compose override that binds the worktree's `backend/`
into the `web` image. Frontend untouched; vitest not required.

## 7. Live verification

If an `openai` `ProviderConfig` with a key exists on the dev DB, run one `ObservationReport`
parse through the facade against `gpt-5.6-sol` from `manage.py shell` and record the outcome
in the summary. This is the only way to prove the API accepts these exact schemas. If no key
exists, the summary says so and the feature is marked unverified live.

## 8. Risks

| risk | mitigation |
|---|---|
| OpenAI strict mode rejects a Pydantic feature in an output model | offline conversion test (§6) + live smoke (§7); if rejected, sanitize the schema in `openai_structured.py` |
| A local server lacks `json_schema` support | `json_object` fallback (§3) |
| A local server rejects `max_completion_tokens` | local uses `max_tokens` (§3) |
| Default bump changes the model for configs with no `default_model` | user-approved; documented in `CLAUDE.md` |
| Old catalog ids removed | none removed |
