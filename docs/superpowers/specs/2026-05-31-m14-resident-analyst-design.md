# M14 — The Resident Analyst — 2026-05-31

**Status:** Umbrella design for a multi-feature milestone. Each feature is
independently shippable and gets its own detailed implementation plan → build
cycle (writing-plans). Build order is dependency-driven (below).

**Origin:** A 6-lens parallel deep-research pass (2026-05-31) over the whole
codebase — daily-workflow friction, AI-capability frontier, market-data/quant
depth, the learning loop / second brain, proactive autonomy, and a contrarian
"big-bets" lens. Twenty-eight grounded proposals collapsed, by **cross-lens
convergence**, into four features the user selected together ("all of those").

This picks up where [[remaining-work]] left off — the M1–M6 improvement program
and M13 prediction ledger are merged; the incremental backlog is exhausted, so
this is **net-new capability**, not surface work over existing pipes.

---

## Guiding thesis: from reactive analyzer to resident analyst

Today the AI **reacts** to one snapshot at a time and **measures** itself
afterward. Independent agents kept surfacing the same four seams where that falls
short of a real analyst you'd retain:

1. **Autonomy is "notify," not "investigate."** *(found independently by the
   AI-frontier and autonomy lenses — the strongest signal)* The agentic tool-loop
   (`get_quote`, `fetch_ohlc`, `search_news`, `get_option_chain`,
   `compute_indicator`, `recall`, `track_record`) is battle-tested in interactive
   chat, but **every autonomous path** (`observer/services/run.py`,
   `triggers/tasks.py`, `briefing`) feeds one static snapshot to **one tool-less
   AI call**. Nothing the system does on its own can pull more data or follow a
   lead. `_resolve_capabilities` (`apps/threads/_request.py`) only enables tools
   off `profile.enable_tools`, and the autonomous callers never set it.
2. **The loop measures but doesn't compound.** `PostMortemReport.lessons` is raw
   `list[str]`, read back by `coach._lessons_block` as the latest two on the
   *exact* ticker — never abstracted into a recurring rule. Calibration is
   measured (`EvalRun`) and *displayed* in the coach (`_calibration_block`) but
   **never acted on**: `router.resolve_provider_and_model` is pure config
   precedence (F6 deferred). And the AI re-derives its view every snapshot.
3. **Reasoning never turns on the human.** The product has an elaborate apparatus
   for grading *the AI* (eval harness, prediction ledger, calibration scorecard)
   and the trader's *stated* convictions (thesis scorecard), but
   `DecisionJournalEntry` already records what the human actually *did* against an
   AI second opinion — and **nothing reads it** to grade the trader's behavior.
4. **The view is amnesiac.** Each observation evaporates into an append-only
   thread; there is no persistent, revised "house view" per name.

**The keystone is the coach.** `assemble_coach_context` (`apps/threads/coach.py`)
is a list of `_safe`-wrapped blocks; "what the AI knows at generation time" grows
by inserting a block, never by refactoring. That is why F2 plugs in surgically,
and why every feature here ultimately routes its new knowledge back through the
same generation path.

---

## Architecture: shared substrate + dependency order

```
F1 Autonomous Investigation ─┬─► builds the bounded-agent-loop primitive (inline)
                             │
F2 Close-the-loop ───────────┼─► new coach blocks + one router tier ─► enriches F1 & F3
                             │
F3 COVERAGE (house view) ◄───┴─► reuses F1's loop (extract on this 2nd use) + renders F2
                             
F4 THE MIRROR ───────────────── independent (pure analytics, zero new models)
```

**The shared substrate is a "bounded autonomous run."** F1 and F3 both need to
run the model agentically without a human watching: tools forced on, a hard
iteration ceiling, a dedicated autonomous cost sub-cap, and stop-flag support.
**Decision (locked): build it inline in F1; extract the reusable primitive when
F3 becomes the second consumer** — YAGNI, second use justifies the abstraction.

**Build order: F1 → F2 → F3, F4 parallelizable.**
- **F1 first** — highest ROI, self-contained, *produces* the bounded-loop
  primitive everything autonomous will reuse.
- **F2 second** — its coach blocks then enrich F1's investigations and F3's
  revisions; the router tier is independent and can land any time.
- **F3 third** — largest; consumes F1's loop and renders F2's track record.
- **F4 anytime** — fully independent; a clean parallel track.

---

## F1 — Autonomous Investigation *(effort: M)*

**Goal:** when something fires (a trigger, an observer schedule, later an
anomaly), the system *investigates* — runs the existing tool-loop, bounded — and
writes a reasoned conclusion, instead of emitting one tool-less observation.

- **Bounded-agent-loop runner** *(NEW — the substrate)* — a run that reuses the
  provider tool-loop already in `apps/ai/providers/claude.py` / `openai.py` (both
  loop on `stop_reason == "tool_use"`) but adds three bounds: a
  `max_tool_iterations` cap (new optional field on `RunRequest`, default `0` =
  unlimited so chat is unchanged; enforced in the provider loop), a per-run
  autonomous cost sub-cap, and stop-flag polling (reuse `apps/threads/stop.py`).
  *Touches:* `apps/ai/types.py` (`RunRequest.max_tool_iterations`),
  `apps/ai/providers/claude.py` + `openai.py` (enforce the cap in the loop),
  new `apps/threads/tasks.py::run_investigation` (lives in the **already-registered**
  tasks module — avoids the Celery-registration trap).
- **Investigation prompt + toolset** *(NEW)* — force `default_toolset()` on
  regardless of `profile.enable_tools`; system prompt asks for a structured
  "what I checked / what I found / what it means / what to watch" conclusion.
  Output persists as an assistant `Message` with `content["kind"]="investigation"`
  in the fire's existing thread; `ToolCall` rows + the `AIRun` row are the audit
  trail (no new model for v1). Streams over the existing `thread.<id>` channel so
  the user can watch it live.
- **Opt-in dispatch from fires** *(NEW)* — a per-trigger / per-schedule
  `investigate: bool` flag (mirrors the existing `structured` / `use_batch`
  booleans). When set, `_do_fire` / observer run dispatch `run_investigation`
  instead of the plain `run_ai_on_message`. *Touches:* `apps/triggers/models.py`
  + `tasks.py::_do_fire`, `apps/observer/models.py` + `services/run.py`.
- **Reply-to-alert (free extension)** — trigger/observer fires already create a
  real thread with a pinned snapshot; enabling tools for *that thread's* follow-up
  turns lets the user interrogate an alert in-place ("is this a fakeout?") and the
  system gathers the answer. *Touches:* `_resolve_capabilities` — flip tools on
  for threads whose origin is an autonomous fire (a `Thread` origin flag/kind).
- **Notification** *(NEW kind)* — `Notification.KIND_CHOICES += "investigation"`.

**Cost discipline:** before dispatch, check the existing
`check_daily_cap`/`check_monthly_cap` (`apps/ai/cost.py`) against a **dedicated
lower autonomous sub-cap** (`AI_AUTONOMOUS_DAILY_CAP_USD`, opt-in) so background
agents can't drain the interactive budget; the `max_tool_iterations` ceiling
bounds a single run. Whole feature is opt-in per trigger/schedule (default off).

**Out of scope (v1):** anomaly-sweep origination (a later autonomy feature),
multi-thread fan-out, a dedicated `Investigation` model/timeline (use `AIRun` +
`ToolCall` for now).

**Risks:** cost runaway → caps + iteration ceiling + opt-in default-off; loop
non-termination → hard ceiling, not model self-judgment; noise → opt-in per
trigger, not global.

**Acceptance:** an opted-in trigger fire produces a multi-tool investigation
message (≥1 `ToolCall`, bounded by the ceiling) with a structured conclusion;
replying in that thread runs tool-backed; total spend respects the autonomous
sub-cap; a notification links to the result.

---

## F2 — Close the learning loop *(effort: M–L, three parts: fast → deep)*

**Goal:** make "the AI gets measurably better over time" real and **acted upon**
— abstract repeated mistakes, give the model an outside-view base rate, and let
measured calibration actually pick the model.

- **(a) Setup-cohort base rates** *(S–M, NEW — no new model)* — at generation
  time, signature the current snapshot into a small feature vector (direction
  under consideration, IV regime from the chain section, days-to-earnings from
  `MarketEvent`, breadth state) and compute the historical decisive hit-rate of
  past `AIPrediction` / `PostMortem` rows sharing that signature. Pure
  SQL/Python aggregation off indexed columns; min-n gate for honesty. Surfaced as
  a new `_cohort_block` in the coach: "calls like this resolved against you 7/10."
  *Touches:* `apps/analytics/services/cohorts.py` (NEW),
  `apps/threads/coach.py` (insert `_safe(lambda: _cohort_block(...))` in the
  `assemble_coach_context` sections list), optional `/api/analytics/cohort/` view
  + a scorecard card.
- **(b) Calibration-weighted routing** *(S, NEW — the deferred F6)* — one new
  resolution tier in `apps/ai/router.py`, gated by
  `AI_CALIBRATION_ROUTING_ENABLED` (default off): among enabled providers with a
  qualifying recent `EvalRun` (min-`scored` floor + recency window), pick the
  best-measured `(provider, model)` (hit-rate, tie-broken by lower
  `calibration_error`); fall through to today's precedence otherwise. Per-send
  override and explicit profile pins still win (precedence preserved). *Touches:*
  `apps/ai/router.py` (`_calibration_choice` helper + one tier),
  `apps/aieval/services.py` (`latest_eval_for_model` already exists).
- **(c) Lesson distillation** *(M–L, NEW app — the anchor)* — a new `apps/lessons`
  app with a `Lesson` model (`text`, `tags` JSON `{sector, catalyst, direction,
  regime}`, `evidence` M2M → `PostMortem`, `support_n`, `last_seen`). A beat task
  `lessons.distill_lessons` reads decisive `PostMortem.report.lessons` +
  `what_missed`, clusters them via the **existing pgvector embeddings**
  (`apps/recall/embeddings.embed` + greedy cosine-threshold clustering: each
  lesson joins the first existing `Lesson` above a similarity cutoff, else seeds a
  new one — deterministic, order-stable) — **decision (locked): embeddings +
  heuristic tags, zero added AI cost, deterministic, look-ahead-safe** — and
  writes/updates `Lesson` rows with running support counts + recency. Tags derive
  deterministically: catalyst from `days_to_earnings`/`MarketEvent`, sector from a
  static map + `CompanyFundamentals.sector`, direction from the source thesis. A
  new `_distilled_lessons_block(snapshot, profile)` matches the **current
  situation's tags** (not just the exact ticker) ordered by support — so a fresh
  biotech-into-earnings snapshot surfaces "you've been too bullish on biotech into
  earnings: 2/9 correct" even on a ticker with no prior theses. A `/lessons`
  management surface lets the user prune/mute (hygiene). *Touches:* new
  `apps/lessons/{models,tasks,services,views,urls}.py`, `config/celery.py`
  (add `apps.lessons.tasks` to the explicit `autodiscover_tasks([...])` list +
  a `beat_schedule` entry), `INSTALLED_APPS`, `config/urls.py` (before generic
  `/api/`), `apps/threads/coach.py` (new block), `frontend` lessons page.

**Look-ahead safety:** distillation and cohorts read **decisive, completed**
rows only (a horizon-H post-mortem completes ≥H days after the thesis opened), so
nothing leaks post-trade info into a contemporaneous call — the same boundary the
eval harness keeps.

**Out of scope (v1):** the best-effort Claude "merge lessons into rules" pass
(a v2 layer over the deterministic clustering); per-lesson confidence learning.

**Risks:** lesson hygiene/noise → support counts + recency decay + prune UI;
cohort small-n → min-n gates + "not enough history yet"; routing staleness →
recency window + min-scored floor.

**Acceptance:** the coach shows a base-rate line on a signature-matched snapshot;
a distilled lesson surfaces on a tag-match across tickers; with calibration
routing on, a run selects the better-measured model and the choice is visible in
the `AIRun`; all gated paths default off / degrade to today's behavior.

---

## F3 — COVERAGE: the living house view *(effort: L)*

**Goal:** each watchlist name gets a single, persistent, version-controlled
"house view" the AI **revises with a reason** instead of re-deriving each
snapshot — a maintained research note, not a chat log.

- **Models** *(NEW app `apps/coverage`)* — `CoverageNote` (latest: `ticker`,
  `stance` bull/bear/neutral, `conviction`, `bull_case`, `bear_case`,
  `key_levels`, `watching_for`, `updated_at`) + append-only `CoverageRevision`
  (`prior`→`new` snapshot of the note, `reason`, `source_observation`/`snapshot`,
  `created_at`). Mirrors the `PostMortem` / decision-journal append-only pattern.
- **Revise-on-observation pipeline** *(NEW)* — any observer fire on a covered
  ticker triggers a structured "revise the standing note given the prior note +
  this snapshot diff" call (`apps/ai/providers/claude_structured.run_structured` +
  a new `CoverageRevision` Pydantic schema), behind a **conviction-hysteresis
  "material change" gate** (using `apps/snapshots/diff.diff_sections` +
  `previous_snapshot_for`) so the view is *revised when earned*, not flip-flopped
  on noise. Keys off the observer's **snapshot**, not its mode — it runs its own
  structured call and so does not require the schedule to be in `structured`
  mode. Dispatched as a cap-gated task `coverage.revise_from_observation`.
  *Touches:* `apps/observer/services/run.py` (post-fire hook), new
  `apps/coverage/{models,schemas,services,tasks,views,urls}.py`, `config/celery.py`,
  `INSTALLED_APPS`, `config/urls.py`.
- **On the substrate extraction (honest note).** The v1 revision is a **single
  structured call** over (prior note + fresh snapshot diff) — the observer
  *already captured* the data, so revision does not inherently need F1's
  bounded loop. Two outcomes, both consistent with the locked decision and with
  YAGNI: (i) if a freshness "gather before revising" step proves worthwhile (e.g.
  check for breaking news since the snapshot), **that** gather is the genuine 2nd
  consumer and triggers extracting F1's inline loop into a shared
  `apps/ai/agent_run.py`; (ii) if revision stays a pure structured call, the
  bounded loop remains inline in F1 and extraction waits for a later consumer
  (War Room / Playbook). We do **not** speculatively extract. The implementation
  plan resolves which path during F3.
- **`/coverage/:ticker` page** *(NEW)* — reads like a maintained equity-research
  note (Initiating / Last-Updated header, evolving thesis, key levels, what-it's-
  watching-for) with a **diffable revision-history slider** ("what did you think
  in March?"). It becomes the natural home that *renders* F2's track record +
  M13 `AIPrediction` history + semantic recall as the note's evidence sidebar.
  *Touches:* `frontend/src/pages/coverage/*`, `router.tsx` (+ `g` shortcut +
  Cmd-K verb), `useCoverage` hook, ledger design tokens.

**Out of scope (v1):** auto-arming a trigger from the note's kill-criterion (a
clean extension once it exists); coverage for non-watchlist names.

**Risks:** view-churn → hysteresis/material-change gate is load-bearing; cost →
one structured call per *material* change, cap-gated; revision quality → the diff
+ prior-note context constrains the model to incremental edits, not rewrites.

**Acceptance:** an observer fire on a covered name produces a `CoverageRevision`
with a stated reason **only** when the change is material (a no-meaningful-change
diff reaffirms without a churn revision); `/coverage/:ticker` renders the current
note + a scrubable history; the note shows live track record + predictions.

---

## F4 — THE MIRROR: grade the human *(effort: M, zero new models)*

**Goal:** turn the calibration apparatus on the *trader's own behavior*, using
data the product already collects but never reads.

- **Behavioral analytics service** *(NEW — established analytics shape)* — a new
  `apps/analytics/services/trader_calibration.py` joining `DecisionJournalEntry ⋈
  Thread ⋈ Thesis ⋈ PostMortem ⋈ AIRun`, on-demand and indexed-column-aggregated
  (no models, no migrations, no Celery). Signals: **AI-override-and-lose** (the
  journal action contradicted the thread's structured call and the realized
  `forward_return_pct` proved the AI right), **conviction inversion** (are your
  5/5 theses actually worse than your 3/5s?), **disposition effect** (cut winners
  / ride losers from journal timing), **revenge-trading** (repeated same-ticker
  re-entries after a loss). Each signal is drillable to the underlying rows and
  hard-gated on min-n. *Touches:*
  `apps/analytics/services/trader_calibration.py` (NEW), `apps/analytics/views.py`
  + `urls.py` (`GET /api/analytics/trader-calibration/`).
- **`/mirror` page** *(NEW)* — the established analytics-service + view + hook +
  page shape (`useTraderCalibration` in `useAnalytics.ts`). Findings framed as
  **tendencies-with-evidence**, surfacing "not enough history yet" rather than
  inventing a pattern. Optional pre-trade nudge at thesis-create when the new
  thesis matches a pattern that has cost the user before. *Touches:*
  `frontend/src/pages/MirrorPage.tsx`, `router.tsx`, `useAnalytics.ts`,
  (optional) `ThesisForm.tsx`.

**Out of scope (v1):** any ML model of the trader; the pre-trade nudge can ship
in a follow-up if the page lands first.

**Risks:** small-n for a single user → hard min-n gates + honest "insufficient
history"; over-reading → frame as tendencies, cite evidence, never a verdict.

**Acceptance:** `/mirror` computes the four signals from existing data with
correct min-n suppression; each card drills to the exact decisions; the
AI-vs-trader divergence signal correctly classifies a known override.

---

## Cross-cutting concerns (the repo's known traps, pre-addressed)

- **Celery registration:** every NEW task module (`apps.lessons.tasks`,
  `apps.coverage.tasks`) MUST be added to the **explicit**
  `autodiscover_tasks([...])` list in `config/celery.py` (no autodiscovery here),
  and `worker` + `beat` need a **restart** to register (they don't hot-reload).
  F1's `run_investigation` deliberately lives in the already-registered
  `apps/threads/tasks.py` to sidestep this.
- **New apps:** `apps.lessons`, `apps.coverage` → `INSTALLED_APPS`
  (`config/settings/base.py`) + `config/urls.py` include placed **before** the
  generic `/api/` include (use the `new-django-app` skill).
- **Section vs snapshot state:** `SnapshotSection` terminal state is `"done"`;
  only the parent `Snapshot` is `"ready"`. Any new section/image filtering must
  use `"done"`.
- **Cost caps everywhere:** all AI-bearing autonomy (F1 investigations, F3
  revisions) checks `check_daily_cap`/`check_monthly_cap` before dispatch, ideally
  against the dedicated autonomous sub-cap. F2's distillation is AI-free by
  decision.
- **Provider access:** obtain providers via `get_provider()` / the router, never
  instantiate directly (F1/F3 reuse the existing run machinery).
- **Look-ahead safety:** F2 distillation/cohorts and any eval-adjacent read use
  decisive, completed rows only.
- **Security model:** no app auth; bind to `127.0.0.1` only; never serialize
  encrypted credential fields. New endpoints are read-only analytics or
  thread-scoped writes — no new auth surface, no `0.0.0.0`.
- **Frontend:** ledger design tokens (no `fg`/`emerald`/`slate`); reuse
  `Skeleton`/`EmptyState`/`ErrorBoundary`/`Toasts`; `*_id` keys on DRF FKs; after
  any re-theme, `make e2e-visual-update`.
- **DB:** new migrations reviewed for reversibility (migration-reviewer); Postgres
  16 + pgvector (the `check` CI Postgres uses `pgvector/pgvector`).

---

## Decisions locked (2026-05-31)

1. **Shared substrate:** build the bounded-agent loop **inline in F1**; extract a
   reusable `apps/ai/agent_run.py` primitive when **F3** becomes the 2nd consumer.
2. **Lesson distillation:** **embeddings + heuristic tags** (deterministic,
   zero added AI cost, look-ahead-safe) for v1; a best-effort Claude "merge into
   rules" pass is a deferred v2 layer.
3. **Build mode:** spec → user review → writing-plans → **autonomous build
   F1→F4 via subagent-driven dev, commit locally only, no push/PR/merge** without
   confirmation; stop to show each feature as it lands.

---

## Testing strategy

- **Unit:** F1 loop bounds (iteration ceiling stops at N, stop-flag aborts,
  sub-cap blocks dispatch); F2 cohort aggregation + min-n suppression, router
  calibration-tier precedence (override/pin still win, fall-through), distillation
  clustering + tag derivation determinism; F3 hysteresis gate (no-meaningful-diff
  → no revision), revision schema; F4 each signal's classification + min-n gates.
- **Integration:** Celery-eager fire → investigation produces a message + tool
  calls + AIRun; observer fire → coverage revision only on material change.
  `run_structured` has **no MOCK_EXTERNAL short-circuit** → patch it directly.
- **E2E (where it touches UI):** `/coverage/:ticker`, `/mirror`, `/lessons` render
  + a11y + visual baselines; the ui lane runs the full suite, so re-grep all
  assertions on any changed serializer shape.
- `make check` gates each feature before its local commit.

---

## Deferred / explicitly not in M14

- Anomaly-sweep origination, EOD/weekly retrospective agents, self-proposing
  triggers, self-tuning observer cadence (the rest of the autonomy lens).
- WAR ROOM (adversarial debate), PLAYBOOK (forward scenarios), Portfolio Risk
  X-Ray / regime classifier / expected-move, the MCP-out server, the consult
  launcher / attach-snapshot-mid-thread workflow set, human-in-the-loop grading,
  calibration-drift sentinel. All remain in the backlog as independent follow-ons;
  several compose naturally on M14's substrate (e.g. War Room reuses the bounded
  loop; the consult launcher complements COVERAGE).
