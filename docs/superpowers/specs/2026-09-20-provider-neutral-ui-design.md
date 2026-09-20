# Provider-neutral UI — visible and configurable — design

**Date:** 2026-09-20
**Status:** implemented on `feat/provider-neutral-ui` (2026-09-20)
**Branch:** `feat/provider-neutral-ui` (off `main` at `59a562be`)
**Follows:** `2026-09-19-provider-neutral-structured-output-design.md` (PR #136, merged)

## 0. Assumptions this spec proceeds under

The request was "update the UI so everything is visible and configurable, with a coherent
design, implemented end to end", given in the worktree that shipped PR #136 with its frontend
untouched. "Everything" is read as: every provider/model/structured-output knob the backend
accepts, and every AI output the backend records, for the surfaces PR #136 touched. Two
adjacent gaps are pulled in because the same forms own them and the e2e suite already
documents them as gaps: the profile's AI feature flags and the schedule's per-fire AI mode.
Anything wider (see §7) is deferred and listed.

## 1. Why

PR #136 made one-shot structured output run on Claude, OpenAI, or a Local endpoint and
refreshed the model catalog. The frontend still assumes the old world:

- A schedule's `override_provider` / `override_model` and `investigate` cannot be set from
  the UI, so the A/B the PR was built for (two structured schedules, one per provider) cannot
  be created without the shell.
- A `consensus_report` message renders as an empty "🤖 Response" — the cross-provider
  agreement signal is invisible.
- Structured fires, post-mortems and War Room verdicts carry no provider/model, so nothing
  tells the user which vendor produced an artifact.
- The profile form exposes none of `enable_tools` / `enable_thinking` / `thinking_budget` /
  `enable_memory` / `enable_coach` / `active`; `ProviderConfig.supports_tools` has no control.
- `lib/modelDefaults.ts` still says `claude-sonnet-4-6` / `gpt-5` while the backend falls back
  to `claude-opus-5` / `gpt-5.6-sol`; the provider card shows the stale id as the effective
  default.
- The scheduled eval hard-codes `provider="claude"` (`analytics/tasks.py`) and the Scorecard
  shows one eval run with no vendor and no history; nothing can start an eval from the UI.

## 2. Goals

1. Every AI knob the backend accepts is settable in the UI, and the UI shows the backend's own
   defaults instead of its own literals.
2. Every AI output shows which provider and model produced it (and its cost where recorded).
3. The A/B flow is completable in the UI: create two structured schedules on one profile with
   different provider overrides, watch their fires with attribution, and compare providers on
   the Scorecard (ledger calibration + eval runs).
4. One design language — the ledger system already used by Settings — across every touched
   page.

## 3. Non-goals

- Streaming `Provider` classes, War Room per-persona provider assignment, TradingView.
- Provider attribution for Regime / Book / Coverage narratives (stored as `TextField`s with no
  metadata home; needs columns — deferred, §7).
- Catalog contents or prices; new routes or side-nav entries.
- Editing `default_watchlist_tickers` on a schedule (unrelated to providers; §7).

## 4. Backend

### 4.1 Catalog endpoint — `GET /api/schwab/models/`

Each row gains `max_payload_tokens`. The response gains a top-level
`defaults: {"claude": DEFAULT_CLAUDE_MODEL, "openai": DEFAULT_OPENAI_MODEL, "local": ""}`
built from `default_model_for`. `?provider=` still filters `models`; `defaults` is always the
full map. The endpoint stays a plain `JsonResponse` view (it is not in `schema.yml` today).

### 4.2 Cross-vendor model guard

`apps/ai/structured.py::_foreign_catalog_model` moves to `apps/ai/catalog.py` as public
`is_foreign_model(provider, model) -> bool` (same semantics: a catalog id owned by another
provider is foreign; an id unknown to the catalog is not). `structured.py` imports it. Three
serializers reject a foreign model with a field error naming the owner:

| serializer | field | provider it is checked against |
|---|---|---|
| `TradingProfileSerializer` | `default_model` | `default_provider` |
| `ProviderConfigSerializer` | `default_model` | `provider` (URL/instance) |
| `ObserverScheduleSerializer` | `override_model` | `override_provider`, else the profile's `default_provider` |

Message: `"{model} is a {owner} model; pick a {provider} model or clear the field."`
Each uses the `_resolved` pattern already in the observer serializer so PATCH with one field
still validates against the stored other field.

### 4.3 Attribution

- `observer/services/run.py::_run_structured_and_record` writes
  `{"kind": "structured_observation", "report": …, "provider": provider_name, "model": model_id}`.
- `observer/services/run.py` resolves the model **once** in a helper `_observer_model(sched, cfg,
  provider_name) -> str`: the first non-foreign candidate of `sched.override_model`, the
  profile's `default_model` (only when the schedule runs on the profile's own provider),
  `cfg.default_model`, else `default_model_for(provider_name)`. The same id feeds the prompt
  hash, the structured run and the prediction stamp (today the hash uses the profile's model
  while the run may use the config's).
- `observer/views.py::observer_thread_view` returns per message
  `"ai_run": {"provider", "model", "cost_usd"} | null` (from the `AIRun` OneToOne; a message
  without a run yields `null`) plus `"status"` and `"error"`, so failed fires and cost-cap
  skips are recognisable. Query stays one `select_related("ai_run")` pass.
- `strategy/warroom/serializers.py::WarRoomRunSerializer.get_messages` adds `"provider"` and
  `"model"` from each message's `ai_run` (null when absent) so persona arguments are
  attributable.
- `thesis/services/postmortem.py`: `pm.report = {**report.model_dump(), "ai": {"provider": target.provider, "model": target.model}}`.
  Pydantic ignores extra keys, so anything re-validating `report` still parses.
- `strategy/tasks.py::run_debate`: the `verdict` dict (and therefore the `warroom_verdict`
  Message that spreads it) gains `"ai": {"provider": target.provider, "model": target.model}`.
- Consensus messages already carry `takes[].provider/model`; unchanged.

### 4.4 Scheduled eval provider

- `SystemSettings.aieval_scheduled_provider = CharField(max_length=32, null=True, blank=True)`;
  migration `core/0005_systemsettings_aieval_scheduled_provider`.
- `config/settings/base.py`: `AIEVAL_SCHEDULED_PROVIDER = env.str(..., default="claude")`
  (a string knob, not an `env.bool` flag — no `feature_flags.py` entry). The
  `AIEVAL_SCHEDULED_MODEL` default moves from `claude-sonnet-4-6` to `claude-opus-5`
  (`DEFAULT_CLAUDE_MODEL`), in `base.py` and the `runtime_config._SPEC` hard default.
- `runtime_config._SPEC` gains `("aieval_scheduled_provider", "AIEVAL_SCHEDULED_PROVIDER", "claude")`;
  the `RuntimeConfig` dataclass gains the field.
- `SystemSettingsView._coerce_setting`: for `ai_failover_provider` and
  `aieval_scheduled_provider` the value must be one of `""`, `claude`, `openai`, `local`
  (400 `invalid_value` otherwise).
- `analytics/tasks.py::run_scheduled`: `provider = rc.aieval_scheduled_provider or "claude"`;
  `model = rc.aieval_scheduled_model`; when `model` is blank or `is_foreign_model(provider, model)`,
  `model = default_model_for(provider)` (a Claude id must never be sent to OpenAI because the
  user only changed the provider). `preflight_cost_cap(provider)` and `evaluate(..., provider=provider)`.

### 4.5 Eval runs — vendor column and manual trigger

- `EvalRun.provider = CharField(max_length=32, default="claude", blank=True)`; migration
  `analytics/0002_evalrun_provider`. `persist_eval_run` writes `result["provider"]` (already
  returned by `evaluate`). `EvalRunSerializer` exposes it. Rationale: a Local model id does not
  identify its vendor, so "the model id identifies the vendor" no longer holds.
- `POST /api/aieval/runs/` (new `EvalRunListCreateView` replacing the list view; GET unchanged).
  Body: `provider` (default `claude`), `model` (default `default_model_for(provider)`),
  `horizon` (default `settings.AIEVAL_SCHEDULED_HORIZON`; must be in
  `settings.THESIS_POSTMORTEM_HORIZONS`), `limit` (default 25, clamped 1–100), `label`
  (default `manual`, ≤64 chars). Validation, in order: provider ∈ choices (400
  `invalid_provider`); `is_foreign_model` (400 `foreign_model`);
  `resolve_structured_target(override_provider=, override_model=)` is `None` (400
  `no_provider`, message says which credential is missing); `ensure_within_caps` raises (409
  `cost_cap`). Success: queue `analytics.aieval_run.delay(provider=, model=, horizon=, limit=, label=)`
  and return 202 `{"queued": true, "provider", "model", "horizon", "limit", "label"}`.
- `analytics.aieval_run` (new `@shared_task`, `acks_late=False, reject_on_worker_lost=False` —
  it bills a provider; mirror `warroom.run_debate`): runs `evaluate(system=DEFAULT_EVAL_SYSTEM, …)`,
  persists with `source="manual"` when `n > 0`, then `notify(kind="eval_done", title=…, body=…,
  link="/scorecard")` (kind ≤16 chars). It is queued, not beat-scheduled, so
  `scheduled_tasks.py` is untouched. A test asserts `acks_late is False`.
- `schema.yml` and `frontend/src/api/schema.d.ts` are regenerated (new POST + `provider` field).

### 4.6 Prediction ledger — one open call per provider and model

The dedup key `(ticker, horizon_days, profile)` collapses two same-profile schedules on
different providers into one open call: the second provider's same-direction call is a no-op
and a flip invalidates the first provider's call. That defeats the A/B. The key becomes
`(ticker, horizon_days, profile, provider, model)`:

- `observer/predictions/services/extract.py`: the `existing` lookup adds `provider=provider,
  model=model`.
- `AIPrediction.Meta.constraints`: the partial unique constraint is replaced by
  `uniq_open_prediction_per_target` over `["ticker", "horizon_days", "profile", "provider",
  "model"]` (`condition=Q(status="open")`, `nulls_distinct=False`). Migration
  `observer/0022_aiprediction_open_call_per_provider_model` removes the old constraint and adds
  the new one (no data step: widening a key cannot create violations).
- Same-direction re-fires on the same target are still a no-op; a flip on the same target still
  invalidates and reopens. `CLAUDE.md`'s ledger line is updated.

### 4.7 Consensus fires feed the ledger

`_run_consensus_and_record` never extracts predictions, so a consensus schedule produces no
ledger rows. `ProviderTake` gains `report: ObservationReport | None = Field(default=None,
exclude=True)` — carried in memory, never serialised into the Message — set by
`consensus_report`. `_run_consensus_and_record(sched, thread, payload_text, *, snap)` then
calls `_extract_prediction(take.report, snap=snap, message=msg, provider=take.provider,
model=take.model, profile=sched.profile)` for every take with a report. With §4.6 each
provider's call lands as its own open prediction, so one consensus schedule is the cleanest
A/B: identical prompt, every provider, per-provider calibration.

## 5. Frontend

### 5.1 Data layer (`src/api`, `src/hooks`, `src/lib`)

- `api/ai.ts`: `AiModel.max_payload_tokens`; `AiModelsResponse = { models; defaults: Record<ProviderId, string> }`;
  `ProviderConfig.supports_tools`. `hooks/useAiModels.ts` adds `useCatalog()` →
  `{ models, defaults, modelsFor(provider), defaultFor(provider), byId }` where `defaultFor`
  returns the API default, falling back to `DEFAULT_MODEL_BY_PROVIDER`.
- `lib/modelDefaults.ts`: `claude: "claude-opus-5"`, `openai: "gpt-5.6-sol"`;
  `DEFAULT_COMPARE_BRANCH` stays `gpt-5-mini` (still the cheapest OpenAI row). The comment
  says these seed state only until `useCatalog().defaults` loads.
- `api/observation.ts`: `ObservationReport` gains the optional fields the backend already
  emits — `predicted_direction`, `predicted_horizon_days`, `predicted_confidence`, `grounding`
  — plus `ProviderTake`, `ConsensusReport`, `AiAttributionInfo = { provider; model }`,
  `PostMortemReportContent`, `WarRoomVerdictContent`,
  `StructuredKind = "structured_observation" | "consensus_report" | "postmortem_report" | "warroom_verdict" | "cached_observation" | "capability_warning" | "investigation"`,
  and the type guard `isConsensusReport(report)` (`"n_providers" in report`).
- `api/observer.ts`: `investigate` on `ObserverSchedule` and `CreateScheduleBody`.
- `api/profiles.ts`: `TradingProfile` + `enable_tools`, `enable_thinking`, `thinking_budget`,
  `enable_memory`, `enable_coach` (all already returned by the API).
- `api/settings.ts`: `aieval_scheduled_provider`.
- `api/thesis.ts`: `PostMortemReport.ai?: AiAttribution`; `api/warroom.ts`: `WarRoomVerdict.ai?`.
- `api/threads.ts` `Message.content`: `kind?: StructuredKind; report?: ObservationReport | ConsensusReport; provider?; model?`.
- New `api/aieval.ts` + `hooks/useAieval.ts`: `EvalRun` (with `provider`), `fetchEvalRuns`,
  `triggerEvalRun(body)`, `useEvalRuns({ refetchInterval? })`, `useTriggerEvalRun()`.
  `useLatestEvalRun` in `useAnalytics.ts` is retyped to `EvalRun`.

### 5.2 Shared AI primitives — `src/components/ai/`

| component | role |
|---|---|
| `ProviderSelect` | `<select>` over Claude / OpenAI / Local. Option text carries readiness from `useProviderConfigs`: `Claude · ready`, `OpenAI · no key`, `Local · no base URL`, `· disabled`. Props: `value`, `onChange`, `id`, `ariaLabel`, optional `emptyOption` (label for `""`, used for "Inherit from profile" and "None"). |
| `ModelFacts` | one mono line under a model select: `$5.00 in · $0.50 cached · $25.00 out per MTok · 1.0M ctx · 150k payload · vision`, plus a copper `default` pill when the id is the provider's catalog default. Unknown ids render `not in catalog — billed at the provider's top rate, 40k payload budget`. |
| `AiTargetPicker` | provider + model side by side. Provider change selects `defaultFor(provider)` when it is in the list, else the first catalog model. Optional `inherit={{ label }}` adds a first provider option that emits `{ provider: "", model: "" }`. Optional `facts`. |
| `AiAttribution` | mono pill `Claude · claude-opus-5` (+ `· $0.0123` when cost given). Provider display names: Claude / OpenAI / Local; unknown providers shown verbatim. |
| `CapabilityHint` | inline copper note: `Claude only — ignored on OpenAI` / `Tool use is off for Local in Settings → AI Providers`. Pure function of `(provider, supportsTools, feature)`. |
| `ModeBadges` | pills for a schedule's AI mode: `full`/`diff`, `structured`, `consensus`, `batch`, `investigate`. |

`components/settings/ModelSelect.tsx` keeps its location, option text (tests pin
`option name === model.name`), `models` override and Custom… input; it gains `ariaLabel`,
`facts?: boolean` (renders `ModelFacts` below) and reads `useCatalog`.
`components/ProviderModelPicker.tsx` (the thread composer's compact picker) keeps its two-select
layout and tests, but lists the fixed provider trio (so **Local** is selectable — today the list
is derived from the catalog, which has no local rows), lands on `pickModelFor(provider)` after a
provider change, and shows a mono text input for the model id when the provider has no catalog
rows (the `(no catalog models — type your own)` option stays as the select's placeholder).

### 5.3 Settings › AI Providers

- `ProviderCard`: default-model fallback comes from `useCatalog().defaultFor(provider)`; hint
  "Used when a profile or schedule doesn't name a model."; `ModelFacts` under the select.
  New "Capabilities" row: for OpenAI/Local two `Toggle`s — `Tool use` (`supports_tools`) and
  `Vision` (`supports_vision`) — saved with the existing Save (draft fields). For Claude a
  static line: `Streaming · tools · structured output · thinking · memory · files · citations · batches`;
  for OpenAI/Local: `Streaming · structured output · tools (toggle) · vision (toggle)`.
  OpenAI gains an optional `Base URL (optional)` field (proxy / Azure-compatible endpoints —
  the serializer already accepts it) and the `Test connection` probe the backend already allows
  for `openai`; both OpenAI and Local show a `Models synced <relative time> · N discovered` line
  from `models_synced_at` / `discovered_models`.
  Preserved: label `"<Provider> API key"`, `Daily cap (USD)`, `Monthly cap (USD)`, `Base URL`
  (Local, exact), `data-testid="provider-card-<p>"`, the `Save` button, the save-body rules the
  tests pin.
- New `components/settings/ModelCatalogPanel.tsx` rendered by `ProvidersSettings` under the
  cards: a `ledger-surface` with eyebrow `Model catalog`, one table per provider (Model — name
  over mono id; Input / Cached / Output $ per MTok; Context; Payload budget; Vision; `default`
  pill). Footnote: "These prices drive cost estimates and caps. A model id that is not listed is
  billed at its provider's top rate and capped at a 40k-token snapshot payload — add it to the
  catalog first." `ProvidersSettings.test` keeps passing (the panel is data-driven and the
  test mocks `ProviderCard` only; the panel reads `useCatalog`, which the test mocks or which
  renders an empty state).

### 5.4 Settings › System

- Failover provider: `ProviderSelect` with `emptyOption="None"`, `ariaLabel="Failover provider"`.
- Scheduled eval: `ProviderSelect` (`ariaLabel="Eval provider"`) + `ModelSelect`
  (`ariaLabel="Eval model"`, Custom… kept). Changing the provider sets the model to
  `defaultFor(provider)`. Horizon becomes a `<select>` over the post-mortem horizons
  (`horizonsFrom`), limit stays numeric (1–100).

### 5.5 Profiles

- `ProfileForm` on ledger primitives (`Field`, `ledger-input`, `ledger-cta`, `Toggle`). Kept
  for e2e/tests: placeholders `Profile name` and `Trading style (used as system prompt)`,
  button text `Create` / `Save` / `Cancel`, `aria-label="Default provider"`, section checkboxes
  labelled by `SECTION_LABELS`, the VIX chip.
- Target: `AiTargetPicker` with facts.
- New fieldset **AI features** — `Toggle`s with exact aria-labels `Enable tools`,
  `Extended thinking` (reveals `Thinking budget` numeric input, min 1024), `Memory`,
  `Decision Coach`. `CapabilityHint` beside thinking/memory when provider ≠ claude, and beside
  tools when the chosen provider's `supports_tools` is off. Toggles stay enabled (the backend
  warns-and-continues); the hint states the consequence.
- `Draft`/`BLANK_DRAFT`/`startEdit`/`submit` carry the five fields (`thinking_budget` default
  8000, matching the model).
- `ProfileList` rows: `AiAttribution`, feature pills (`tools`, `thinking`, `memory`, `coach`),
  an `Inactive` pill when `!active`, and an `Activate` / `Deactivate` button (PATCH `active`;
  hint text "Active profiles sort first"). A 400 from the vendor guard surfaces as a toast.
- e2e: `test_profile_flags_editable_in_ui` and `test_profile_toggle_active` lose their strict
  `xfail` markers; the activate test clicks `Deactivate` then expects `Activate` (the seeded
  profile is active). `e2e/pages/profiles.py` docstring updated.

### 5.6 Schedules

Split `SchedulesPage.tsx` into `pages/schedules/{ScheduleRow,CreateScheduleForm,ScheduleAiFields,ScheduleSectionsEditor}.tsx`
+ `useScheduleForm.ts`; the page file keeps the default export.

- Create form, new fieldset **AI**: `AiTargetPicker` with
  `inherit={{ label: "Inherit from profile — Claude · claude-opus-5" }}` (label computed from
  the selected profile's defaults; aria-labels `Override provider` / `Override model`);
  payload shape select (kept); checkboxes `Structured (typed observation card)` (kept),
  `Cross-model consensus…` (kept; needs Structured), `Messages Batch…` (disabled unless the
  resolved provider is Claude, hint `Claude only — Messages Batches`), new
  `Investigate (bounded tool loop, plain mode only)` (disabled when Structured). A footer line
  shows the effective target: `Runs on Claude · claude-opus-5 (from profile)` /
  `(override)`. Body adds `override_provider`, `override_model`, `investigate`.
- Row: second line `ModeBadges` + `AiAttribution` of the effective target with `(override)` or
  `(profile)` qualifier; buttons `Run now`, `Sections`, new `AI`, `Delete`. `AI` toggles a
  `ScheduleAiFields` editor bound to the row that PATCHes
  `{override_provider, override_model, mode, structured, consensus, use_batch, investigate}`
  via new `useUpdateSchedule`. The row header keeps exactly one checkbox (`enabled`).
- Ledger primitives throughout; preserved: h1 `Observer schedules`, `+ New schedule`, labels
  `Name` / `Profile`, `Create` (exact), `data-testid="schedule-row-<id>"`, `Run now`,
  `aria-label="delete <name>"`, `Sections`, `SkeletonRows`, EmptyState copy.

### 5.7 Observer timeline and thread detail

- New `components/ConsensusReportCard.tsx`: header pill = modal bias (colours shared with
  `ObservationReportCard` via an exported `BIAS_COLOR`), agreement `2 of 3 agree (67%)` or the
  degraded note; `Divergent — do more homework` copper pill when `divergent`; takes list
  (`AiAttribution` + bias pill); per-ticker grid (ticker × provider → bias, with agreement);
  `SaveCardButton`.
- `ObserverTimelinePage`: `Message` gains `ai_run` and content `provider/model/kind/report`;
  headline `📊 <headline>` (structured), `🧭 Consensus — <bias> · <n> providers` (consensus),
  `🤖 Response` (plain, word kept for the existing test); each row shows `AiAttribution`
  (+cost) from `ai_run` else content; expanded body renders the matching card. h1 stays the
  thread title.
- `StreamingMessage` + `useLiveMessages`: `kind` union; `consensus_report` renders the card;
  `postmortem_report` renders a `PostMortemReportBody` (summary, what worked, what missed,
  lessons, would-repeat — the review thread today shows an empty bubble); `warroom_verdict`
  renders a `WarRoomVerdictBody` (verdict, confidence, strongest bull/bear, falsifier);
  `cached_observation`, `capability_warning` and `investigation` get a header chip (`cached`,
  `warning` in loss tone, `investigation`) over the plain text. `provider/model` fall back to
  `content.provider/model` when `ai_run` is absent.
- `ObservationReportCard` renders the AI's directional call when present —
  `Call: bullish · 5d · 72%` — and `grounding` as small chips; this is the line that becomes an
  `AIPrediction`, so it must be visible where the report is.
- Timeline rows treat **every** `role: "system"` message as a notice (🔒, dimmed) — today only
  text starting with `⏸` qualifies, so cost-cap skips (`Observer fire skipped at …`) and
  `no key configured` rows render as `🤖 Response`; `status: "failed"` rows show a `failed`
  pill and the `error` text.
- `ThreadDetailPage` seeds the composer picker from the thread's profile
  (`thread.profile.default_provider/default_model`) when present, else the catalog default.
- New `ConsensusReportCard.stories.tsx` and `settings/ModelCatalogPanel.stories.tsx` (the
  story-coverage ratchet counts storyless components in those directories).

### 5.8 Scorecard — Offline eval

Move the eval block into `pages/scorecard/EvalSection.tsx` (+ `EvalRunForm.tsx`,
`EvalRunsTable.tsx`), used by `ScorecardPage`:

- **Runs table** (`useEvalRuns`): date, `AiAttribution`, label · source, n / scored, hit-rate,
  Brier, calibration error. Clicking a row selects it; the reliability table (today's
  `EvalCalibration`) renders for the selected run, defaulting to the latest.
- **Run eval** form: `AiTargetPicker` (facts), horizon `<select>` (`horizonsFrom`), limit
  (1–100), label. Warning line: "Makes up to {limit} billed calls on {Provider}. Skipped
  automatically if that provider's cost cap is hit." Submit → POST → toast
  `Eval queued — it appears in the table when it finishes.`; the table refetches every 15 s
  for 3 minutes after a queue. 400/409 bodies surface as toasts.
- Empty state when there are no runs. `useLatestEvalRun` remains the default-selection source
  so `ScorecardPage.test`'s spies keep working.

### 5.9 Post-mortem, War Room and the second opinion

`PostMortemCard` header shows `AiAttribution` when `report.ai` is present; `WarRoomDetailPage`'s
verdict block does the same for `verdict.ai`, and each persona lane shows the provider/model
that argued it (`WarRoomMessage` gains `provider`/`model`, §4.3). `AISecondOpinion` (the AI's
live call shown on the thesis form) appends `AiAttribution` from the `ai-view` payload's
`provider`/`model`, which it already receives.

## 6. Design language

- Surfaces `ledger-surface p-5`; card titles `font-display text-[1.05rem] text-ink-50`;
  labels through `Field` (mono 10px uppercase copper); inputs `ledger-input`; primary action
  `ledger-cta`; secondary/ghost `ledger-ghost`; pills `ledger-pill` (`data-tone` copper /
  gain / loss); switches `Toggle`; failure text `text-loss`.
- Touched pages drop `slate-*`, `emerald-*`, `rose-*`, `bg-ink-850 border-rule` ad-hoc inputs
  in favour of the tokens above.
- Provider display names: Claude, OpenAI, Local. Model ids always `font-mono`. Attribution
  format `Provider · model-id`.
- Claude-only capabilities are labelled `Claude only`, never hidden or silently disabled;
  provider-dependent controls that the backend would reject (Messages Batch off-Claude) are
  disabled with the reason inline.
- Layout works at phone width (existing pages already stack; new tables scroll horizontally in
  a `min-w-0 overflow-x-auto` wrapper).

## 7. Deferred (explicitly out of scope)

- Provider/model columns for `RegimeReading`, `BookSnapshot`, `CoverageRevision` narratives.
- `default_watchlist_tickers` editor on schedules.
- `TradingProfile.default_model` DB default (`claude-sonnet-4-6`) → catalog default (needs a
  migration; only affects ORM-created profiles).
- A `provider` filter on the Scorecard's ledger calibration section (the API already groups by
  provider/model; a filter is cosmetic). A profile/schedule filter on the live AI calibration
  (per-provider rows already separate the A/B arms once §4.6 lands).
- `AgentPreset.structured` has no consumer (the composer applies only `objective_template`) —
  a dead knob to wire or remove separately.
- Structured post-mortem `AIRun`s are invisible to the Scorecard's "Provider calibration"
  (it joins `AIRun.message__thread`; one-shot runs have no message).
- Briefing `synthesis_text` is the rendered user prompt, not the AI reply (`BriefingRun.
  synthesis_message` points at the user Message) — a separate bug.
- `thinking_delta` WS events are typed but never rendered.
- Clearing a `SystemSettings` override back to "inherit" (the API takes `null`; the UI never
  sends it) and showing overridden-vs-inherited state.
- Storybook fixtures that still name `claude-sonnet-4-6` / `gpt-5` (cosmetic).

## 8. Testing

**Backend (pytest, `-p no:randomly`)** — models endpoint fields + defaults; `is_foreign_model`
moved (existing facade tests pass); guard accept/reject on each of the three serializers
(same-vendor and unknown ids accepted, foreign rejected, PATCH of a single field validated
against the stored counterpart); observer thread endpoint `ai_run` present/null; structured
record stamps provider/model; post-mortem and war-room `ai` stamps; `runtime_config` provider
field and PATCH validation of the two provider knobs; `run_scheduled` routes provider and
falls back on a foreign model; `POST /api/aieval/runs/` 202/400/400/400/409 with the task
queued with the right kwargs; `aieval_run` persists `provider` and notifies; `acks_late is False`;
`EvalRunSerializer.provider`; `_observer_model` candidate order and foreign fallback; timeline
`status`/`error`; War Room messages carry `provider`/`model`; ledger dedup keeps two open calls
for two providers on one ticker/horizon/profile and still no-ops a same-target re-fire;
consensus fire extracts one prediction per take with that take's provider/model.

**Frontend (vitest, unit project)** — `ProviderSelect` readiness text; `ModelFacts` default
pill and unknown-id line; `AiTargetPicker` inherit emits blanks and provider change picks the
default; `ProviderCard` includes `supports_tools` in the save body and shows the API default;
`ModelCatalogPanel` rows; `SystemSettings` PATCHes the two provider selects; `ProfileForm`
posts the five flags, hints on non-Claude; `ProfileList` Activate PATCH; `SchedulesPage`
create posts overrides/investigate, batch disabled for an OpenAI profile, row `AI` editor
PATCHes; `ObserverTimelinePage` consensus card + attribution + system notices + failed pill;
`StreamingMessage` consensus / post-mortem / verdict bodies and kind chips;
`ObservationReportCard` call line; `ProviderModelPicker` lists Local and shows a text input for
catalog-less providers; `EvalSection` table/select/POST; `PostMortemCard` / `WarRoomDetailPage`
/ `AISecondOpinion` attribution. Fixtures
that pinned `claude-sonnet-4-6` as *the default* move to `claude-opus-5`; option-name
assertions are untouched.

**Gates** — backend `ruff`, `ruff format`, `mypy`, `lint-imports`, `deptry`, repo semgrep
rules; `make schema` + regenerated `schema.d.ts`; frontend `pnpm lint`, `pnpm test:cov`
(80/74/77/82), `pnpm depcruise`, `pnpm type-coverage`. e2e is not run in this session; the
two profile xfails are flipped in code, and the visual baselines for `profiles`, `schedules`,
`settings_general`, `observer_timeline` will need `make e2e-visual-update` after merge.

## 9. Risks

| risk | mitigation |
|---|---|
| e2e selectors drift | §5 lists the preserved labels/roles/testids per page; the row keeps a single checkbox |
| Visual snapshots differ | expected; regenerate after merge (advisory lane) |
| Manual eval bills real calls | cap preflight at POST time plus in the task; explicit warning line; single-user desktop app |
| A stale `schema.d.ts` slips through | regenerate via the documented `docker compose cp` route and confirm `git diff --stat` |
| `SchedulesPage` / `ScorecardPage` grow past C901-style limits | both split into page subfolders |
