# Improvement Program — 2026-05-30

**Status:** Roadmap / decomposition. Umbrella for a multi-milestone "do it all" program.
Each milestone is independently shippable and gets its own detailed spec → plan → build cycle.

**Origin:** A 5-lens parallel deep-research pass (2026-05-30) over the whole codebase
(AI intelligence, second-brain workflow, market-data depth, reliability/infra/cost, UX/frontend).
All five lenses reported; the AI-depth lens (M6) is folded in below.

This supersedes the open items in [[product-improvement-audit]] and folds in its "remaining
themes" (live capture console, trust/observability, retention). The 2026-05-29 **Decision Coach**
(merged PR #36) already closed the headline "AI is stateless / learn-loop open" gap by injecting
base prompt + theses + snapshot-diff + recall + per-ticker track-record into the generation path.

---

## Guiding thesis: substrate vs. surface

Independent agents kept finding the same anti-pattern — **expensive capability is built and tested,
then hidden or discarded one layer before it reaches the consumer.** Verified instances:

- `track_record_for_ticker()` (`apps/analytics/services/calibration.py`) — per-ticker W/L + conviction
  hit-rate. Has **no DRF endpoint and zero frontend references**; only the AI prompt sees it.
- Per-contract **gamma/theta/vega** are normalized and stored in `OptionChainSnapshot.payload`
  (`apps/market/services/chain.py`), then `_render_chain` shows the AI **only delta + IV**; no GEX/
  max-pain/skew/term computed.
- `snapshot.<id>` WS channel — backend broadcasts per-section capture progress
  (`apps/snapshots/services/__init__.py`), **no frontend subscriber** (verified): emitted into the void.
- `ObservationReportCard` (typed bias/levels/risks) renders **only** on the timeline page; the main
  consult thread shows flat markdown (`StreamingMessage` never reads `content.kind`/`report`).
- `?since=` reconnect-replay buffer — server fully wired (`apps/threads/event_log.py`,
  `ThreadConsumer`), **frontend never sends `since=`** → events silently lost on WS reconnect.
- The **Dashboard** is "a polished welcome mat, not a command center" — shows a market strip +
  ephemeral broker positions + recent triggers; surfaces **none** of theses / observer / briefing.

Consequence for sequencing: the hard machinery exists (recall/pgvector, calibration+Brier, greeks
normalization, WS broker w/ backoff, `apps/market/returns.py`, `diff_sections`, the `ObservationReport`
schema). Most of M1/M3/M5 is **surface work over existing pipes** → S/M. The two real L's (M2's
ingestion+backtester, M4 Portfolio) are where new persistent state/history is created.

---

## Milestones

### M1 — Visible Second Brain (+ coach upgrades)  *(effort: M)*
**Goal:** make already-built-but-hidden intelligence visible AND make the coach good+ubiquitous in one
pass. W1–W4 below + the three pulled-forward coach items (W5 coverage audit, W6 semantic recall, W7
lessons block, W8 coach-on-triggers — detailed in the M1 spec).

- **Track record at decision time** *(S, NEW)* — `GET /api/analytics/track-record/?ticker=&direction=&conviction=`
  wrapping the existing tested `track_record_for_ticker()` (zero new logic). `useTrackRecord` hook;
  render inline in the thesis form ("last 5 NVDA calls: 3W/2L") and as a card on `ThesisDetailPage`.
  *Touches:* `apps/analytics/{urls,views}.py`, `frontend/src/hooks/useAnalytics.ts`,
  `frontend/src/pages/thread-detail/ThesisForm.tsx`, `ThesisDetailPage.tsx`.
- **Structured-observation cards in the main thread** *(S–M, OVERLAPS ObservationReportCard)* —
  teach `useLiveMessages`/`Conversation` to detect `content.kind === "structured_observation"` and
  render `ObservationReportCard` (markdown fallback). Re-theme the card off `emerald/rose/slate` to
  ledger tokens. *Touches:* `frontend/src/pages/thread-detail/{useLiveMessages,Conversation,types}.tsx`,
  `frontend/src/components/ObservationReportCard.tsx`.
- **Live capture progress** *(S–M, DEEPENS-BACKLOG: dead snapshot WS)* — subscribe
  `SnapshotComposerPage` to `snapshot.<id>` via `useChannel` + a `SnapshotCaptureProgress` checklist
  (quotes ✓ / chain ✓ / news ⏳); keep the HTTP poll as terminal source of truth. Decide `?since=`:
  wire the client to send `since=<lastSeq>` on reconnect, **or** delete the `event_log` dead code +
  update CLAUDE.md §3.3. *Touches:* `frontend/src/pages/SnapshotComposerPage.tsx`,
  `frontend/src/realtime/WebSocketProvider.tsx`, `frontend/src/hooks/useChannel.ts`.
- **Command-center Dashboard + live tiles** *(M, DEEPENS-BACKLOG)* — replace the lower grid with
  tiles for open theses vs. target (reuse the briefing's `pct_to_target`), observer today + next fire
  (`useSchedules`), briefing one-liner (`useLatestBriefing`), armed triggers + latest firings, and a
  7-day events row (`useUpcomingEvents`). Add one aggregating endpoint to avoid N round-trips. Add
  `notifications` to `pathForChannel`, promote `NotificationBell`'s raw socket to the shared `Broker`,
  and have tiles react to `user.anonymous.notifications` live. *Touches:* `frontend/src/pages/Dashboard.tsx`
  + new `components/dashboard/*Tile.tsx`, `WebSocketProvider.tsx`, `NotificationBell.tsx`; new
  aggregating view (e.g. `apps/thesis` action or a small `apps/briefing`-style endpoint).
- **Coach coverage check** *(S, verify)* — confirm `assemble_coach_context` reaches interactive
  follow-up turns / all thread entry-points, not just create-time + observer. If a gap exists, wire it.

**Acceptance:** track record visible where decisions are made; structured cards render in-thread;
capture shows live per-section progress; the dashboard shows theses/observer/briefing/triggers and
updates without a manual refresh.

### M2 — Signal Depth  *(effort: L)*
**Goal:** deepen the raw material every observation reasons over, and turn the backtester into a signal-quality lab.

- **Options analytics layer** *(S–M, NEW — best value/effort in the program)* — `apps/market/services/option_analytics.py`
  computing put/call vol+OI, max-pain, 25-delta IV skew, ATM term structure, and dealer GEX from greeks
  **already stored** in `OptionChainSnapshot.payload`. New `chain_analytics` sub-section + renderer;
  extend the `unusual_options` card. *Touches:* `apps/market/services/option_analytics.py`,
  `apps/snapshots/serializer.py` (`_render_chain`), `apps/snapshots/services/__init__.py`,
  `apps/analytics/services/unusual_options.py`.
- **Fundamentals section + trigger leaves** *(M, DEEPENS-BACKLOG)* — `apps/market/services/fundamentals.py`
  via Finnhub `/stock/metric?metric=all` + `/stock/profile2` (clone the `news.py`/`events.py` pattern),
  24h cache, persisted to `CompanyFundamentals`. New `fundamentals` snapshot section + renderer; DSL
  leaves `pe_ratio`/`market_cap`/`revenue_growth`/`gross_margin` (ticker-required, compare-only, **not**
  backtestable). Attach to thesis context. *Touches:* `apps/market/{services/fundamentals.py,models.py}`,
  `apps/snapshots/{services/__init__.py,serializer.py}`, `apps/triggers/{dsl,metrics}.py`, `apps/thesis`.
- **Real breadth & relative-strength** *(M, NEW)* — replace the price-only breadth section with computed
  internals (adv/decl, % of universe above 50/200-DMA from `OHLCBar`) + sector RS vs SPX + primary-ticker
  RS vs sector vs SPX. *Touches:* `apps/market/services/context.py` (rewrite `_fetch`), new
  `apps/market/services/breadth.py`, `apps/snapshots/serializer.py` (`_render_breadth`); reuse
  `returns.py` + `apps/triggers/indicators.py`.
- **Cross-asset macro tape** *(S, NEW)* — always-on block: 10y, DXY, oil, gold via ETF proxies
  (TLT/UUP/USO/GLD that Schwab quotes reliably) + optional BTC via Finnhub (mild off-spec). *Touches:*
  `apps/market/services/context.py`, `apps/snapshots/serializer.py`.
- **Freshness / staleness signaling** *(S, NEW)* — stamp each section with `fetched_at`/age + a
  per-section provenance banner; `OHLCBar` gap detector ("history has a 3-session hole"). *Touches:*
  `apps/snapshots/services/__init__.py`, `serializer.py`, `apps/market/cache.py`.
- **Scheduled time-series ingestion** *(M, NEW — multiplier)* — beat task: daily `OHLCBar` for
  watchlist + sectors + macro proxies, periodic `OptionChainSnapshot` for watchlist names. Unblocks
  breadth/RS, backtester, `unusual_options` IV-z, and leaderboard coverage (all currently starved by
  capture-only history). *Touches:* `apps/market/tasks.py`, `config/celery.py`; reuse `_persist_bars`.
  **Pairs with M3 retention.**
- **Backtester v2** *(M, DEEPENS-BACKLOG)* — add vix/cross-asset leaves via aligned bars; IV-z replay
  over `OptionChainSnapshot` history (coverage-gated, honest); forward-return scoring per match via
  `returns.trading_day_forward_return_pct` so it answers "did the signal *work*." *Touches:*
  `apps/triggers/backtest.py`, `apps/triggers/views.py`; reuse `returns.py` + `unusual_options` IV math.

**Acceptance:** chain analytics + fundamentals + real breadth/RS + macro render into the AI payload;
ingestion job populates history; backtest returns forward-return summaries with coverage honesty.

### M3 — Trust & Reliability  *(effort: M)*
**Goal:** make the unattended scheduler fleet robust, cheap, and observable.

- **Self-hosted error aggregation** *(M, DEEPENS-BACKLOG — best value here)* — `core.ErrorEvent` model
  + a structlog processor / Celery `task_failure` signal persisting `level>=ERROR`; surface on `/errors`
  or via the bell. (observer/trigger/backup/briefing/recall all catch-and-log to stdout today.)
- **Provider retry/backoff + optional failover** *(S–M, NEW)* — SDK `max_retries` + retryable-status
  guard on the AI run path; respect the Redis stop flag; don't double-bill once tokens stream; optional
  fallback to secondary provider via `router.resolve_provider_and_model`. *Touches:* `apps/ai/providers/*`,
  `apps/threads/{_stream,tasks}.py`, `apps/ai/router.py`.
- **Celery hardening** *(S, NEW)* — `task_time_limit`/`task_soft_time_limit`, `task_acks_late` +
  `task_reject_on_worker_lost` (idempotency-audited first), `worker_max_tasks_per_child`, `result_expires`;
  HTTP read timeouts on provider clients. *Touches:* `config/celery.py`, `apps/ai/providers/*`.
- **Retention / pruning** *(M, DEEPENS-BACKLOG)* — `core.prune_retention` beat: age-based trim of
  `OHLCBar`/`OptionChainSnapshot`/`Notification`/old backups (FK-safe). Optional: offload
  `SnapshotImage.data` bytes from Postgres to `/data` (shrinks every `pg_dump`). *Touches:* new
  `apps/core/tasks.py`, `config/celery.py`; (offload) `apps/snapshots/{models,views,serializer}.py`.
- **Ops hardening** *(S, mixed)* — `make reload-workers` + dev watch parity for worker/beat; weekly
  `backups.verify_latest` (`pg_restore --list` into a scratch namespace → record on `BackupRecord`);
  point healthcheck at `/api/ready/` (DB+Redis) instead of always-200 `/api/health/`. *Touches:*
  `Makefile`, `compose*.yaml`, `apps/backups/{tasks,services}.py`, `apps/core/views.py`.

**Acceptance:** failures across the schedulers are queryable in one place; a transient provider 5xx
retries instead of killing an observer fire; workers can't hang forever; tables/backups stay bounded.

### M4 — Portfolio  *(effort: L)*
**Goal:** the one genuinely-new object — close the *opinion → position → outcome* loop. Fully
observational (manual entry; no broker write path).

- **`apps/portfolio`** *(L, DEEPENS-BACKLOG audit #4)* — `Position` (+optional `Lot`): `ticker`,
  `thesis` FK (the linking edge), `direction`, `quantity`, `avg_cost`, `opened_at`/`closed_at`,
  `realized_pnl`, `status`, `note`. Unrealized P&L computed on read via `returns.nearest_bar_close`;
  holding return via `returns.forward_return_pct`. Serializer/viewset/urls (follow the new-Django-app
  convention). `PortfolioPage` + a real "The Book" dashboard tile (replacing the ephemeral broker table).
  Optional: seed a `Position` from a closed thesis or `Snapshot.manual_positions`; recall kind `"position"`.
  *Touches:* new `apps/portfolio/*`, `config/settings/base.py`, `config/urls.py`, `frontend` page + tile;
  reuse `apps/market/returns.py` (do not inline P&L).

**Acceptance:** positions persist independent of broker connection, link to theses, and show deterministic
unrealized/realized P&L; calibration can later weight outcomes by conviction *and* size.

### M5 — Polish  *(effort: M)*
**Goal:** consistency + power-user ergonomics.

- **Ledger-theme migration** *(M)* — bring ~8 off-theme pages (`SchedulesPage`, `SnapshotComposerPage`,
  `ThreadsPage`, `Watchlists*`, `Triggers*`, `ObserverTimelinePage`) and shared primitives
  (`EmptyState`/`Skeleton`/`CommandPalette`/`ShortcutHelpDialog`) onto ledger tokens. Verify tokens
  against `tailwind.config.ts` (invalid tokens silently drop); regenerate visual baselines.
- **Command-palette verbs + global search** *(M)* — parameterized actions ("new snapshot of $TICKER",
  "observe watchlist", "open thesis for $X", "run briefing"); route empty-query input to `recallSearch`
  so Cmd-K doubles as global search. *Touches:* `AppLayout` `useDefaultCommands`, `CommandPalette.tsx`.
- **Interactive thesis charts** *(M)* — `ThesisChart` wrapping the existing `lightweight-charts` `Chart`
  with `addPriceLine` for target/invalidation; embed on `ThesisDetailPage` (keep the PNG render path for
  AI/export).
- **Print/export a single observation** *(S–M)* — `SaveCardButton` via the existing `html2canvas`
  pattern on `ObservationReportCard`/`PostMortemCard`/thesis masthead; print stylesheet.
- **Per-page `document.title`** *(S)* — `useDocumentTitle` fed from the breadcrumb `handle.crumb`.

### M6 — AI Depth  *(effort: M–L)* — folded in from the AI-depth lens (2026-05-30)
**Goal:** the next layer of AI quality *beyond* the Decision Coach — better retrieval, outcome-feedback,
self-critique, and a way to **measure** prompt/model changes instead of guessing.

- **Semantic coach recall** *(S, DEEPENS Decision Coach/recall)* — `coach._recall_block`
  (`apps/threads/coach.py:174-187`) calls `related_to_ticker()` = pure recency (`ORDER BY
  -source_created_at`), ignoring the embedding entirely. Swap to the existing semantic `search()`
  (`apps/recall/services/search.py:38-46`) seeded by a situation query (snapshot headline + open-thesis
  text), `kinds=["postmortem","thesis","observation"]`, ticker-scoped, recency tiebreak. Highest
  quality-per-token win; FTS fallback + `_safe()` degrade cleanly.
- **Lessons-learned block** *(S, DEEPENS Decision Coach)* — post-mortem `lessons`/`what_missed` reach
  generation only incidentally. Add `_lessons_block(ticker)` rendering top-2 decisive `PostMortem`s
  (verdict correct/incorrect) × 2 bullets w/ verdict+horizon. Look-ahead-safe by construction
  (post-mortems complete ≥ horizon after open; coach reads only `status="done"`). *Touches:*
  `apps/threads/coach.py` (lazy import `apps.thesis.models.PostMortem`).
- **Coach on the trigger path** *(S, DEEPENS Decision Coach)* — `apps/triggers/tasks.py:184-195` posts a
  bare `serialize_for_ai` user turn (no `assemble_coach_context`), unlike observer/ThreadViewSet. Add the
  coach block; triggers fire exactly when priors matter most. With M1/W5 (plain-chat + follow-ups) this
  closes the **"coach everywhere"** gap.
- **Offline eval harness** *(L, NEW — the meta-tool)* — new `apps/aieval/`: labels = `Thesis ⋈ PostMortem`
  (done, decisive, has `forward_return_pct`); replay a candidate (system_prompt, model) against the
  **frozen** source snapshot via `run_structured(ObservationReport)`; score directional hit + Brier using
  `calibration.py` helpers. Management command + one read-only view. **Look-ahead leakage is the core
  hazard** — serialize the snapshot as-of capture, no post-trade coach context; gate behind manual run +
  cost caps + `--limit`. Turns every other idea here from vibes into measured deltas. *Reuses:*
  `claude_structured.run_structured`, `ObservationReport`, `calibration` Brier/hit-rate, `serialize_for_ai`,
  `returns.py`.
- **Self-critique pass** *(M, NEW)* — opt-in red-team second pass on the structured observer path: feed the
  first `ObservationReport` back ("argue against each signal; flag ungrounded claims; revise confidence") →
  revised report. `TradingProfile.enable_critique`; prompt-cache the snapshot; ~2× cost (opt-in);
  Claude-only initially. *Touches:* `apps/ai/providers/claude_structured.py`,
  `apps/observer/{services/run.py,schemas.py}`, `apps/profiles/models.py`. Pair with the eval harness to prove it.
- **Calibrated confidence, surfaced** *(M, DEEPENS calibration scorecard)* — `Signal.confidence` is never
  reconciled with reality. (a) Inject "your stated confidence has historically been X% accurate in bucket Y"
  into the coach (reuse `_prob_for_conviction`/`PROB_MAP`/by-bucket hit-rate); (b) persist stated confidence
  at thesis-creation (small nullable col) so the scorecard gains an AI-confidence calibration curve.
  *Touches:* `apps/threads/coach.py`, `apps/analytics/services/calibration.py`,
  `apps/thesis/{models,services/postmortem}.py` (+migration).
- **Provider-consensus signal** *(M, NEW; OVERLAPS Compare)* — opt-in observer mode fanning the structured
  report across 2-3 provider+model pairs (reuse compare fan-out) → deterministic agreement/divergence card
  ("3/3 bullish NVDA; split on SPY"). *Touches:* new `apps/observer/services/consensus.py`,
  `apps/observer/schemas.py` (`ConsensusReport`), `ObserverSchedule` flag. Cost ×N (caps enforced);
  non-Claude needs JSON-mode structured or restriction.
- **Richer ObservationReport + grounding tools** *(M, DEEPENS ObservationReport/tools)* — add
  `predicted_direction`/`predicted_horizon_days` + `grounding: list[str]` (Optional/additive) so every
  structured observation becomes self-labeling for the eval harness; add a `recall` tool variant with
  `kinds`/`ticker` filters + a `track_record` tool. *Touches:* `apps/observer/schemas.py`,
  `apps/ai/tools/registry.py`, `apps/analytics/services/calibration.py`.

**Agent's build-only-one:** the **eval harness**, shipping **semantic coach recall** first as its inaugural
measured win.

**DECISION (user, 2026-05-30): the three S-effort coach items — semantic recall, lessons block, and
coach-on-triggers — are PULLED FORWARD into M1** (as W6/W7/W8; coverage audit = W5). They strengthen the
coach M1 makes visible and all touch `coach.py`. M6 therefore retains: eval harness, self-critique,
calibrated confidence, provider-consensus, richer ObservationReport/tools, **plus** the two harder coach
gaps M1 defers (coach on snapshot-free plain chat; per-follow-up-turn refresh).

---

## Sequence & dependencies

```
M1 (visible) ─┬─> M4 (portfolio uses M1 dashboard + returns.py)
              └─> M5 (polish builds on M1 surfaces)
M2 (signal depth): ingestion ─> breadth/RS, backtester v2, IV-z
M3 (reliability): independent — can interleave; retention pairs with M2 ingestion
M6 (AI depth): after the afb1 agent reports; independent of M1–M5
```
**Recommended order:** M1 → M2 → M3 → M4 → M5 → M6. M3 may jump ahead of M2 if hardening-before-features
is preferred. Each milestone is its own PR; reorder/pause/kill between milestones.

## Execution method (per milestone)
1. **Spec** → `docs/superpowers/specs/2026-05-30-m<n>-<topic>-design.md`.
2. **Plan** → `docs/superpowers/plans/2026-05-30-m<n>-<topic>.md` (TDD, task-by-task).
3. **Build** via subagent-driven development: each task = failing test → impl → per-task review.
   Subagents read/test in their own contexts (immune to the parent's display flakiness this session).
   **Forbid subagent git-state ops** (commits only; no `git pull`/`checkout`).
4. **Verify centrally** — a verification subagent runs `make check`; report pass/fail before merge.
5. **Branch per milestone off `origin/main`**; checkpoint with the user **before first code** and
   **before any push/PR**.

## Risk register
- **Tool-output display flakiness (this session)** → lean on subagents whose final reports return intact.
- **Finnhub free tier** shared across news/events/fundamentals → 24h cache + pacing.
- **Sparse chain/IV history** until ingestion lands → coverage-gate backtester/IV features honestly.
- **Retention** must be FK-safe (don't delete OHLC a post-mortem still needs).
- **`acks_late`** requires a per-task idempotency audit first.
- **Theme migration** invalidates visual baselines → `make e2e-visual-update`.
- **Coach coverage** on interactive turns unconfirmed → M1 verify / M6 detail.

## Tracker
- [ ] M1 Visible Second Brain — spec / plan / build / verify / PR
- [ ] M2 Signal Depth — spec / plan / build / verify / PR
- [ ] M3 Trust & Reliability — spec / plan / build / verify / PR
- [ ] M4 Portfolio — spec / plan / build / verify / PR
- [ ] M5 Polish — spec / plan / build / verify / PR
- [ ] M6 AI Depth — spec / plan / build / verify / PR  *(lens folded in 2026-05-30)*
