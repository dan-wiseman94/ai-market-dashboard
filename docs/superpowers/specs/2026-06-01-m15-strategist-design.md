# M15 — "The Strategist"

**Written 2026-06-01.** Umbrella design for the milestone that grows the
*resident analyst* (M14) into a *strategist*. Same shape as the M14 doc: one
umbrella spec, four feature sub-designs (F1–F4), a plan per feature.

## The throughline

Every reasoning surface built through M14 shares two properties:

- **Bottom-up and per-ticker.** `CoverageNote`, `Thesis`, `AIPrediction`, and
  every observer report key off a *single* ticker. Nothing reasons about the
  *macro weather* or the *whole book at once*.
- **Single-voice.** Each question gets *one* AI pass. Nothing institutionalizes
  disagreement, even though the multi-provider `compare` fan-out and the M14
  bounded tool-loop could power it.

M15 closes exactly those two gaps, then adds the autonomy capstone that ties the
new surfaces together. The four features form a **producer → consumer**
dependency graph, so they are built **foundation-first** and compound:

```
F1 Regime  ──(context)──▶  F2 Book X-Ray ──(the "book" object)──▶ F4 Anomaly-sweep
    │                            │                                      ▲
    └──────(regime-aware)────────┴────▶ F3 War Room ──(escalation target)┘
```

1. **F1 Regime engine** — a top-down `RegimeReading` the coach, Book X-Ray, War
   Room, and Anomaly-sweep all *consume*.
2. **F2 Portfolio Risk X-Ray** — the whole-book object (reads `current_regime()`).
3. **F3 War Room** — adversarial debate service (debates a thesis / coverage
   stance / book risk; regime-aware from day one).
4. **F4 Anomaly-sweep autonomy** — the capstone: originates investigations,
   frames them against regime + book, and can escalate a finding into a War Room
   or a coverage revision.

## Shared architecture & principles

- **Four new apps**, each per the repo's "Adding a Django app" convention
  (`AppConfig` with short `label`, `urls.py`, `INSTALLED_APPS` entry, a
  `config/urls.py` include placed **before** the generic `/api/` include):
  `apps.regime`, `apps.book`, `apps.warroom`, `apps.desk`.
- **Hybrid reasoning everywhere** — a deterministic core (computed, reproducible,
  no key needed) + an optional best-effort AI narrative that degrades to `""` on
  no key / cap hit / any exception. The house pattern (`postmortem.objective_verdict`
  + the morning briefing). Each deterministic sub-computation is independently
  best-effort and reports honest `coverage` rather than fabricating
  (`leaderboard.coverage_pct` rule).
- **Beat tasks** are registered in `config/celery.py`'s explicit
  `autodiscover_tasks([...])` list and gated for market-hours *inside the task
  body* via `apps.observer.services.market_hours` (the existing convention — the
  schedule is a plain crontab). New task modules / `beat_schedule` entries need
  `docker compose restart worker beat` (worker/beat don't hot-reload).
- **Cost discipline** — every AI call routes through `get_provider()` and is
  cap-checked (`check_daily_cap` / `check_monthly_cap`); agentic loops are bounded
  by `max_tool_iterations`. Autonomy that spends money is **opt-in, default-OFF**
  (the `AIEVAL_SCHEDULED_ENABLED` precedent — `run_structured` has no
  `MOCK_EXTERNAL` short-circuit).
- **Notifications** use the v1 anonymous channel `user.anonymous.notifications`.
- **DRF serializers** expose FK ids as `*_id`; frontend TS uses those keys verbatim.
- **Landmines to respect** (from CLAUDE.md): `config/urls.py` include ordering;
  dashboard `_safe(fn, default)` defaults must be full contract-valid shapes;
  snapshot **section** terminal state is `"done"` (only the parent `Snapshot` is
  `"ready"`); the synthetic-first-user-turn pattern for feeding context to the AI
  pipeline; never log encrypted creds; never bind `0.0.0.0`.

---

## F1 — Regime engine

**Goal.** Classify the market environment on a cadence, inject it into the coach
so every observation / prediction / coverage revision is regime-aware, and alert
on regime *change*. A context-multiplier: it lifts every existing AI surface.

**Inputs (pure composition over existing services — no new data plumbing).**
- `apps.market.services.context.fetch_market_context()` → `$SPX`/`$QQQ`/`$VIX`
  last, the 11 sector ETFs (offensive vs defensive leadership), `$ADVN/$DECN/
  $TICK/$TRIN` breadth (best-effort), `relative_strength`, `sector_rotation`.
- `apps.market.services.fred.fetch_macro()` → full Treasury curve incl.
  `T10Y2Y` (curve inversion) + 10Y level/direction. Gated on the optional FRED key.
- `OHLCBar` for `$VIX` (level + percentile over history) and `$SPX` (vs 50/200dma
  via the `apps.triggers` indicator helpers `sma_spread_pct` / `dist_from_sma_pct`).

**Axes (each independently best-effort; degrades with an honest `coverage` note).**

| Axis | Source | Labels |
|---|---|---|
| Volatility | `$VIX` level + percentile | Low / Normal / Elevated / Stress |
| Trend | `$SPX` vs 50/200dma + slope | Uptrend / Range / Downtrend |
| Breadth | `$ADVN/$DECN/$TRIN` (best-effort) | Broad / Mixed / Narrow / Deteriorating |
| Leadership | offensive (XLK/XLY/XLC) vs defensive (XLU/XLP/XLV) ratio | Offensive / Defensive / Mixed |
| Rates *(opt, FRED)* | `T10Y2Y` shape + 10Y direction | Inverted / Steepening / Easing / Tightening |

A deterministic rule folds the *available* axes into a **composite**:
`Risk-On / Neutral-Transitional / Risk-Off / Stress`. A best-effort Claude pass
writes a one-paragraph `narrative` ("Risk-off: VIX 28 @ 87th %ile, SPX below
50dma, breadth deteriorating, defensive leadership"); degrades to `""` with no key.

**Data model** — `apps.regime.RegimeReading`:
`created_at`, `composite` (char/choices), `axes` (JSON `{vol, trend, breadth,
leadership, rates}` each `{label, value, coverage}`), `drivers` (JSON), `narrative`
(text), `inputs` (JSON snapshot of raw values for reproducibility), `changed_axes`
(JSON list — which axes flipped vs the prior reading). Thresholds live in one
documented `apps/regime/constants.py` (tunable later; no config singleton — YAGNI).
Accessor `current_regime()` → latest reading (or `None`).

**Production** — `regime.refresh` beat task (crontab every ~30 min; market-hours
guard inside the body, plus one forced pre-open + one post-close reading)
persists a `RegimeReading`. When `composite` or a key axis flips vs the prior
reading, emit a `Notification` ("Regime change: Risk-On → Risk-Off — VIX spike +
breadth deterioration"). On-demand recompute via `POST /api/regime/refresh/`.

**Coach integration** — a new `_regime_block(reading)` in `apps/threads/coach.py`,
added to the section list of **both** `assemble_coach_context` (snapshot path)
**and** `assemble_coach_context_for_message` (bare-chat path). It is the first
**ticker-independent** coach block, so it renders even on a snapshot-free chat
with no `$cashtag` — a bonus deepening of the A2 bare-chat coach. Reads
`current_regime()`; `""` when no reading exists. Lazy cross-app import
(`apps.threads` → `apps.regime`) per the import-cycle discipline.

**API + UI** — `GET /api/regime/` (latest + history), `GET /api/regime/current/`,
`POST /api/regime/refresh/`. A Dashboard regime **tile** (composite + color +
one-line driver) and a `/regime` **page** (per-axis breakdown + a regime-history
timeline). Dashboard tile section default must be a full contract-valid shape.

**Out of scope (v1).** Per-ticker regime sensitivity (that's F2's regime-fit);
regime *backtesting*; ML regime models; intraday tick-level regime.

---

## F2 — Portfolio Risk X-Ray ("The Book")

**Goal.** Reason over the *whole book at once* — concentration, correlation
clusters, regime fit, invalidation clustering, hedge gaps — the cross-sectional
view every per-ticker surface lacks.

**The book (union definition).** Every ticker the user has *any* stance on, from
three sources, de-duped by ticker:
- `portfolio.Position` (open) — literal, in dollars.
- `thesis.Thesis` (open) — `direction` + `conviction` + invalidation.
- `coverage.CoverageNote` — `stance` + `conviction`.

Unified metric: **conviction-weighted directional exposure** — signed by
long/short (a `bear`/`short` is negative), weighted by `conviction` (1–5), so the
book is meaningful even with zero logged dollar positions. Actual `$` exposure
(`quantity × last`) is shown as a secondary readout when a `Position` exists.
Positions with no conviction inherit the linked thesis's conviction, else a
documented default.

**Analyses (deterministic core + best-effort AI synthesis).**
- **Concentration** — conviction-weighted exposure by ticker; net long/short;
  "top 3 names = 60% of conviction-weighted exposure."
- **Correlation clusters** — pairwise return correlation from `OHLCBar` (reuse
  `apps.market.returns`; ~60–90 trading-day daily-return window); cluster by a
  correlation threshold; only names with sufficient overlapping history are
  clustered (honest `coverage_pct`). Headline insight: *"NVDA/AMD/AVGO/TSM are one
  bet, not four — 70% of your longs."*
- **Regime fit** — reads `current_regime()` (← F1): *"offensive-leadership book
  into a Risk-Off / defensive regime."*
- **Invalidation clustering** — theses whose `invalidation_price` / note cluster
  near one level: *"4 of 6 theses stop out if SPX breaks 5800 — one event flattens
  the book."*
- **Hedge / balance gaps** — net exposure; absence of shorts/hedges.

**Data model** — `apps.book.BookSnapshot`: `created_at`, `as_of_date` (unique
per day), `exposures` (JSON: per-ticker {direction, conviction_weight, dollar,
sources}), `clusters` (JSON), `concentration` (JSON metrics), `regime_fit` (JSON,
references the `RegimeReading` id used), `invalidation_clusters` (JSON),
`narrative` (text, best-effort), `coverage` (JSON honesty notes).

**Production** — `book.snapshot_daily` beat task persists one `BookSnapshot`/day
(unique `as_of_date` claim in `transaction.atomic()`, the briefing-claim pattern).
On-demand recompute via `POST /api/book/recompute/` (caches the AI synthesis).
**Alerts** — when concentration or regime-fit deteriorates materially vs the prior
snapshot, emit a `Notification`. The morning briefing (`apps.briefing`) gains a
deterministic **book-risk section** sourced from the latest `BookSnapshot`
(wrapped so it never raises, like every other briefing section).

**API + UI** — `GET /api/book/` (latest X-Ray + history), `POST /api/book/recompute/`.
A dedicated `/book` **page** (it spans theses + coverage + positions, broader than
the positions-only `/portfolio` page) + a "top book risk" Dashboard tile.

**Composition downstream.** `BookSnapshot` is the object **F3 War Room** debates
("is this concentration a problem?") and **F4 Anomaly-sweep** flags against
("book just became 90% one cluster").

**Out of scope (v1).** True dollar-VaR / beta-to-SPX factor models; options-greek
book aggregation; tax-lot accounting; auto-suggested hedges (a War Room subject /
F4 suggested action instead).

---

## F3 — War Room

**Goal.** Institutionalize disagreement. Given a subject, run adversarial AI
voices that argue to a synthesized verdict + confidence — attacking the solo
trader's deepest blind spot: no one to disagree.

**Key reuse — a debate is a thread with multiple voices.** A War Room run is a
`threads.Thread` with `kind="warroom"` whose `Message`s are persona-tagged
(`content["persona"]`), so it rides the entire existing pipeline (`thread.<id>`
streaming, `cost` events, the `?since=` replay buffer, cost attribution) for free
and streams into the UI live. The subject context enters as a synthetic first
user turn (the documented pinned-snapshot pattern). No bespoke transcript model.

**Subjects (polymorphic).** A `Thesis`, a `CoverageNote` stance, a `BookSnapshot`
risk (← F2), or a free-form question. Invoked by a "Convene War Room" button on
those pages + `POST /api/warroom/convene/`. F4 can convene one programmatically.

**Voices.** `bull / bear / skeptic` advocates + a `synthesizer`, each a role with
its own system prompt and a regime-aware coach block (← F1).

**Per-run choices (the convene form is the control surface — defaults make the
common path one click).**
- **Voice mode** *(default: multi-provider-when-available)* — assign personas to
  different providers for genuine diversity when >1 provider is configured + in
  budget, else all on the default provider. Reuses the `compare` precedent.
- **Structure** *(default: rebuttal)* — `judge-panel` (parallel opening →
  synthesis), `rebuttal` (opening → one rebuttal round, each voice sees the others
  → synthesis), or `deep` (opening → N rebuttal rounds to a max cap). Bounded by a
  hard round cap.
- **Grounding** *(default: on)* — each voice uses the M14 bounded tool loop
  (quotes / news / recall) to cite evidence; "quick take" turns tools off.

**Verdict.** The synthesizer emits a structured result via `claude_structured`
(Claude-only; non-Claude degrades to a plain-text verdict message):
`{verdict, confidence, strongest_bull, strongest_bear, what_would_change_my_mind}`.

**Data model** — thin `apps.warroom.WarRoomRun`: `thread` (FK), nullable subject
FKs (`thesis` / `coverage_note` / `book_snapshot`) + `free_prompt` (text), `params`
(JSON: voice_mode / structure / grounding / provider assignments), `verdict`
(JSON), `confidence` (float), `status`, `created_at`. Verdict is **read-only in
v1** — surfaced and linked to the subject; the human decides whether to act
(auto-revising coverage from a verdict is F4 territory).

**Cost control.** Bounded rounds × bounded tool iterations × bounded voices; each
voice's run is cap-checked like any AI run; the convene form shows an est. cost
band per structure choice.

**API + UI** — `POST /api/warroom/convene/`, `GET /api/warroom/runs/`,
`GET /api/warroom/runs/:id/`. A `/warroom` launcher + a **bespoke courtroom view**
(a column per voice + a verdict card), with "Convene War Room" buttons on
thesis / coverage / book pages. The debate streams live via the existing
`thread.<id>` WS.

**Out of scope (v1).** Auto-acting on a verdict; human-graded debates; persisting
per-round token telemetry beyond the existing per-message cost; >1 simultaneous
subject per run.

---

## F4 — Anomaly-sweep autonomy (capstone)

**Goal.** The AI stops waiting to be asked. A periodic sweep detects anomalies
across the things you care about, contextualizes them against regime + book,
originates bounded investigations, and surfaces findings with one-click actions.

**Universe.** Watchlist + covered + open-thesis + open-position tickers (not the
whole market).

**Detector registry (all four buckets ship v1; each reuses existing computation).**
- **Options flow** — `analytics.unusual_options` (volume/oi ≥ 3, IV z ≥ 1.5σ).
- **Price / technical** — gaps, 52-week extremes, large pct-change (reuse the
  `triggers` indicator metrics).
- **Macro / regime** — an F1 regime *change* as a top-priority origination event;
  index-vs-breadth divergence (best-effort breadth).
- **Book & coverage hygiene** — F2 `BookSnapshot` deterioration
  (concentration / cluster / regime-fit); covered names that moved materially but
  weren't revised; covered names reporting earnings soon (`MarketEvent`) with a
  stale view.

Each detector returns candidates `{type, ticker?, severity, evidence}`.

**Flow.** opt-in market-hours-aware `desk.sweep` beat → run detectors over the
universe → score by `severity × how-much-you-care (conviction / position size) ×
novelty` → dedup against a per-`(ticker, type)` cooldown → take **top-K** (and
`log()` what was dropped — no silent truncation) → originate **K separate bounded
investigations** (reuse M14 investigation mode: a thread with relevant context,
tools on, capped) → write each finding to the **Desk feed** + notify material ones.

**Agency — Suggest, one-click to act (human-in-the-loop).** Each finding carries
one-click **suggested actions** the user approves:
- "Convene War Room" → F3 `convene` on the relevant subject.
- "Revise coverage to X" → the existing `apps.coverage` `revise_coverage` service.
- "Open thesis" → prefilled thesis form.

No auto-execution in v1 (auto-convene / auto-revise is the deferred "Auto" level).

**Data model** — `apps.desk.DeskEntry`: `created_at`, `anomaly_type`, `ticker`
(nullable for book-level), `severity` (float), `evidence` (JSON), `investigation`
(FK to the `Thread`), `finding` (text), `suggested_actions` (JSON), `status`
(new / acted / dismissed). Only top-K-that-became-entries persist; raw candidates
are ephemeral.

**Guardrails.** `ANOMALY_SWEEP_ENABLED` default **OFF** (the autonomy-spends-money
rule); per-sweep top-K cap; a daily origination/cost cap (mirrors observer cap
resolution); per-`(ticker, type)` cooldown; tunable detector thresholds in
`apps/desk/constants.py`; every action auditable in the feed.

**API + UI** — `GET /api/desk/` (feed), `POST /api/desk/:id/act/` (execute a
suggested action), `POST /api/desk/:id/dismiss/`, `POST /api/desk/sweep/` (manual
run, unguarded by the enabled flag like the manual briefing run). A `/desk`
**feed page** (chronological: anomaly → finding → suggested actions) + an
unread-count Dashboard tile. Reuses `Skeleton` / `EmptyState` primitives.

**Composition.** F4 is where the milestone closes: it *reads* F1 (regime-change
detector + regime-aware investigations) and F2 (book-deterioration detector), and
*invokes* F3 (War Room escalation) and `coverage.revise_coverage` — the four
features become one self-directing loop.

**Out of scope (v1).** Auto-execution of suggested actions; self-proposing
triggers; self-tuning observer cadence; whole-market (non-universe) scanning;
EOD/weekly retrospective agents (all remain backlog follow-ons).

---

## Testing

- **Unit** (the deterministic cores — the bulk of the value, no AI needed):
  regime axis classification + composite folding (`parametrize` over input
  fixtures); book exposure unification + correlation clustering + invalidation
  clustering; anomaly scoring + dedup/cooldown; War Room verdict parsing. Each
  best-effort sub-computation tested for graceful degradation (missing axis /
  thin history → honest coverage, never raises).
- **Integration** (Celery eager, `fakeredis`, real Postgres incl. `pgvector`):
  beat tasks persist + alert + respect caps and the `ANOMALY_SWEEP_ENABLED` gate;
  regime-change Notification fires only on a flip; book daily-claim is idempotent;
  desk cooldown prevents re-investigation. **`run_structured` has no
  `MOCK_EXTERNAL` short-circuit → patch it directly.** Never set `MOCK_EXTERNAL`
  on the dev stack.
- **E2E** (the UI surfaces): `/regime`, `/book`, `/warroom`, `/desk` render +
  a11y + visual baselines; the `ui` lane runs the full suite, so re-grep all
  assertions on any changed serializer shape. After re-theme, regenerate visual
  baselines (`make e2e-visual-update`; root-owned).
- `make check` gates each feature before its local commit.

## Build sequence & conventions

- **Foundation-first:** F1 → F2 → F3 → F4. One branch per feature off
  `origin/main` (local main lags ~150 commits). Commit **locally only** — no
  push / PR / merge without explicit confirmation (standing directive). Push, when
  asked, as dan-wiseman94: `env -u GITHUB_TOKEN git push`.
- Each new app: `INSTALLED_APPS` + a `config/urls.py` include **before** the
  generic `/api/`; add task modules to `config/celery.py`'s explicit list;
  `docker compose restart worker beat` after adding tasks/schedule entries.
- TDD via subagent-driven development; implementer → reviewer subagents run
  **sequentially** (concurrent reviewers misfire on uncommitted SHAs); subagent
  prompts forbid git-state ops (commits only).
- Frontend: ledger design tokens (`ink`/`copper`/`rule`); reuse
  `Skeleton`/`EmptyState`/`ErrorBoundary`/`Toasts`; new routes nest under
  `<AppLayout>` with a `handle.crumb`; derive state in render (no `setState` in
  effects — eslint errors).

## Deferred / explicitly not in M15

- The **"Auto" agency level** for F4 (auto-convene / auto-revise without approval).
- Self-proposing triggers, self-tuning observer cadence, EOD/weekly retrospective
  agents, anomaly-sweep over the whole market — the rest of the autonomy lens.
- The **MCP-out server** (expose coverage / theses / recall / predictions to
  external agents), **Playbook** (forward scenario trees), **Expected-move**
  overlay, calibration-drift sentinel, consistency sentinel — independent
  follow-ons that compose on M15's substrate.
