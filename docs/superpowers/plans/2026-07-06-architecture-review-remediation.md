# 2026-07-06 — Architecture review remediation

## What this is

A full-repo architecture review produced 64 adversarially-verified findings across backend
service layers, Celery/observer design, realtime, API design, frontend, testing/CI, and doc
drift. This plan is the record of how that review's fixes are batched and landed on
`fix/architecture-review`. Each batch is an independent implementer brief; the briefs
themselves are working artifacts of the review run (not checked into `docs/superpowers/`) and
are summarized here so the batch structure has a durable record in this repo.

## Batch structure

Batches are grouped by subsystem so each implementer touches one coherent area and its own
tests, minimizing merge conflicts on a shared checkout:

- **B01** — data-model: the `Notification.kind` varchar(16) overflow silently dropping
  prediction-invalidation notifications.
- **B02** — capture-flow: unbounded observer-thread history replayed into every AI call;
  Compare-branch prompt contamination; token-counting/embedding work inside
  `transaction.atomic()`.
- **B03** — service-layer / celery-design: observer structured-path `InvalidToken` handling,
  a transient Redis error permanently disabling a trigger, trigger cooldown races, prediction
  dedup race, observer fire overlap guard.
- **B04** — ai-abstraction / capture-flow: observer batch runs bypassing `AIRun`/cost caps,
  Claude-only paths accepting non-Claude providers, zero-usage accounting on aborted streams,
  the token-count cache's sync calls inside `lru_cache`, raw Anthropic clients skipping shared
  resilience kwargs, Messages-Batch mode's cost-ledger and snapshot-data gaps.
- **B05** — service-layer / celery-design: provider-gate policy duplication, `run_ai_on_message`
  lacking a service-layer form, War Room orchestration living in the task module, uncaught
  `SoftTimeLimitExceeded` stranding war-room runs.
- **B06** — service-layer / celery-design / capture-flow: non-atomic coverage-note + revision
  writes, prod overlay running worker/beat under dev settings, stale-claim recovery gaps,
  queue/tick-size mismatches, unrecoverable stuck `AIPrediction.resolving`.
- **B08** — api-design: a sliced-queryset 404 on notification retrieve, OpenAPI contract blind
  spots, synchronous LLM calls inside request handlers, inconsistent pagination/list envelopes,
  a thesis-list N+1, FK-naming drift from the `*_id` convention.
- **B09** — realtime / security-ops: dev-stack WS origin validation as a no-op, terminal WS
  broadcasts emitted inside an open transaction, no gap-detection on replay-buffer overflow,
  inconsistent event envelope conventions across channels.
- **B10** — ai-abstraction / security-ops: the prompt-injection data-boundary directive missing
  from several live AI run paths (contradicting the prior CLAUDE.md claim), an infra exception
  mid-stream stranding a message in `streaming` and dropping billed usage.
- **B11** — app-boundaries / data-model / completeness-critic: `threads/coach.py` layering
  inversion, market-domain math homed in `observer`, `observer` doubling as the platform
  notification bus, `model_bases.TimeStamped` dead code + a docstring drift, structlog coverage
  gaps, three inconsistent trading-day boundary definitions, an overstated Sentry-coverage
  comment, seven hand-rolled Redis clients.
- **B12** — testing-ci: local `make test` running under `dev` settings instead of `test`, the
  realtime WS e2e lane still advisory, the dead perf lane, a stale workflow comment, the
  advisory patch-coverage gate, a CI-unreachable prod-posture guard test.
- **D01** (this batch) — docs drift: CLAUDE.md's market-hours location and mock-tooling claims,
  spec §5's capture-pipeline drift beyond the already-acknowledged chord-vs-loop line, the
  README backup/restore story, and this plan doc.
- **F01** — api-design / frontend: unused generated FE types with a hand-written contract that
  has already drifted, two coexisting error envelopes with only one parsed, query errors
  rendering as eternal skeletons or false empty states.
- **F02** — realtime / frontend: a backend replay contract claiming client-side seq dedupe the
  frontend never implements, the thread WS event union typed `any`, a refetch race that can
  clobber an in-flight streaming branch, hardcoded model-id defaults duplicated across files,
  `useChannel` resubscribing on unmemoized handler identity.

## Scope discipline

Each batch's brief names its expected path scope; touching outside it is allowed only when a
fix genuinely requires it, and must be called out in that batch's report. Batches share one
checkout on `fix/architecture-review`, so each commits only its own explicit paths — no
`git add -A`/`-u`, no staging another batch's in-flight files.

## Status

Batch reports (status, commits, tests run) are produced per-batch by each implementer and
rolled up by the coordinator; this plan records structure and scope, not per-batch outcomes.
