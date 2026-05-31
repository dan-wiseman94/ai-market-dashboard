# Remaining Work — after the M1–M6 "do it all" program

**Written 2026-05-31.** Reference doc for picking up after a context clear. The
M1–M6 improvement program (from the 2026-05-30 5-lens audit) is **merged to
`main`** — PRs #38(M1) / #39(M2) / #40(M3) / #41(M4) / #42(M5) / #43(M6), plus
#44 (two post-merge integration fixes: `apps.portfolio` INSTALLED_APPS +
snapshots `0010` events/fundamentals choices migration).

Umbrella spec: `docs/superpowers/specs/2026-05-30-improvement-program-design.md`.
This file is the "what's left" companion — every item below was **verified
against the merged code on 2026-05-31** (grep results in parentheses), not just
recalled.

The program is substantively complete. What remains splits into three tiers.

> **UPDATE 2026-05-31 — "M7: Eval-driven calibration loop" is BUILT** (local branch
> `feat/m7-eval-calibration-loop`, not yet pushed). Implemented in dependency order
> B1 → B3 → B2 → schedule → A3: `predicted_confidence` on `ObservationReport`;
> `EvalRun` model + migration + read-only `/api/aieval/runs/` (+ `/runs/latest/`);
> `preflight_cost_cap` wired into the manual command (which now persists an
> `EvalRun`); an opt-in, cost-capped `aieval.run_scheduled` beat task (default OFF
> via `AIEVAL_SCHEDULED_ENABLED`); and `_calibration_block` injecting the latest
> measured calibration into the live coach. Items marked **✅ DONE** below.
> Still open: **A1**, **A2**, and all of **Tier C**. Plan:
> `docs/superpowers/plans/2026-05-31-m7-eval-calibration-loop.md`.

> **UPDATE 2026-05-31 (cont.) — M7 merged (#46) + 7 more items shipped.** After M7
> merged (PR #46, with a CI fix: the `check` Postgres now uses `pgvector/pgvector`,
> since `apps.recall`'s migration runs `CREATE EXTENSION vector`), the following
> were built and PR'd:
> - **C6** scorecard drill-down + a "Model eval calibration" card — merged (#47).
> - **C4** pre-trade discipline: `rationale` + an invalidation (price OR new
>   `invalidation_note`) now **required** on thesis create — merged (#48).
> - **C5** watchlist "what changed since your last look" per-ticker expander — merged (#50).
> - **C1** cross-provider failover before the first token, opt-in
>   `AI_FAILOVER_ENABLED`/`AI_FAILOVER_PROVIDER` — open (#52).
> - **A1** `?since=` WS reconnect-replay wired client-side in `WebSocketProvider` — open (#54).
> - **C7** image-bytes offload to the `/data` volume (`SnapshotImage.file_path` +
>   `apps.snapshots.image_store`, disk-first read, DB fallback) — open (#55).
> - **C2** observer response-cache for byte-identical prompts, opt-in
>   `OBSERVER_RESPONSE_CACHE_ENABLED` — open (#56).
>
> **Still genuinely open: A2** (coach on snapshot-free chat — needs a brainstorm
> on the no-snapshot "situation" definition) and **C3** (news quality /
> corporate-actions: splits & dividends distorting the returns math — needs a
> data-source decision, e.g. Finnhub, and touches `apps/market/returns.py`, which
> feeds post-mortems, the leaderboard, and the scorecard drill-down, so it wants
> a careful, focused session).

---

## Tier A — Deliberately deferred during the program (flagged, not faked)

Each was skipped because it needs a design decision, not just execution.

### A1. `?since=` client-side reconnect replay  (M1 / W3) — ✅ SHIPPED (#54)
- **State:** server side fully built — every `thread.<id>` event carries a Redis
  `INCR` `seq`; `ThreadConsumer` parses `?since=<seq>` and replays a 256-event
  capped tail. **Client never sends `since=`** → a WS gap on reconnect still
  silently drops events. (Verified: no `since=` in `frontend/src/realtime/`.)
- **Why deferred:** needs a `WebSocketProvider` refactor — track last-received
  `seq` per channel + distinguish first-connect from reconnect in
  `openForChannel`, append `?since=` only on reconnect. Documented in CLAUDE.md.
- **Effort:** S–M (frontend). **Files:** `frontend/src/realtime/WebSocketProvider.tsx`.

### A2. Coach on snapshot-free chat + per-follow-up-turn refresh  (M1 → M6)
- **State:** `assemble_coach_context` injects at all 3 snapshot-bearing entry
  points (threads view / observer / trigger `_do_fire`) but returns "" when the
  snapshot has no `primary_ticker` — so a bare chat thread with no snapshot is
  un-coached, and follow-up turns inherit the stale create-time block rather
  than refreshing. (Verified: coach keys off `snapshot.primary_ticker`.)
- **Why deferred:** needs a "situation" definition when there's no snapshot
  (what does the coach retrieve against?) + a token-budget call for per-turn
  refresh. That's a brainstorm, not a clean build.
- **Effort:** M. **Files:** `backend/apps/threads/coach.py`, `_request.py`.

### A3. Live calibration/confidence injection into the coach  (M6-3 follow-on) — ✅ DONE
> `apps/threads/coach.py:_calibration_block(profile)` reads the latest `EvalRun`
> for `profile.default_model` and injects a measured hit-rate/Brier + an
> over/under/well-confident verdict; wired as the last section of
> `assemble_coach_context` (rides the existing primary-ticker gate). Touches only
> the live coach — the eval replay path stays look-ahead-safe.
- **State:** M6 *measures* calibration (the `apps/aieval` harness +
  `confidence_calibration`) but the coach does NOT *read* it at generation time.
  (Verified: `coach.py` imports `track_record_for_ticker` but no calibration
  curve / `_prob_for_conviction`.)
- **Why deferred:** depends on B3 (persist EvalRun) + a scheduled harness run so
  there's a stored, current calibration to inject. Chicken-and-egg with B.
- **Effort:** S once B3 exists. **Files:** `backend/apps/threads/coach.py`.

---

## Tier B — Altitude/robustness gaps the `/simplify` review surfaced (small, real)

### B1. `predicted_confidence` on `ObservationReport` — ✅ DONE
- M6-5 added `predicted_direction` + `predicted_horizon_days` (verified present
  in `observer/schemas.py`) but **no paired confidence**. The eval harness
  reconstructs confidence from `mean(signal.confidence)` — leaky: a report with
  0 signals scores `confidence=None` and is dropped from the reliability curve.
- **Fix:** add `predicted_confidence: float | None = Field(default=None, ge=0, le=1)`
  (Optional/additive per the schema's own contract); `aieval` uses it directly,
  falls back to the signal mean. **Effort:** S. **Files:**
  `backend/apps/observer/schemas.py`, `backend/apps/aieval/services.py`.

### B2. aieval cost-cap pre-flight — ✅ DONE
- Real `manage.py aieval` runs are guarded only by `--limit`, not
  `check_daily_cap`/`check_monthly_cap`. (Verified: no cap call in
  `apps/aieval/`.) The command docstring implies cap-respect → either wire a
  pre-loop `check_daily_cap("claude", ...)` in the command's `handle()`, or
  correct the docstring to say "use `--limit`". **Effort:** S.

### B3. `EvalRun` persistence + read-only view — ✅ DONE
- The harness prints/returns results; nothing stores them. (Verified: no
  `EvalRun` model, no `apps/aieval/views.py`.) Needed before A3 (live injection)
  or any scorecard UI for eval results. **Effort:** S–M (model + migration +
  one DRF view). **Files:** new `apps/aieval/models.py` + `views.py` + `urls.py`.

---

## Tier C — Audit ideas never scoped into M1–M6 (independent one-offs)

The 2026-05-30 5-lens audit surfaced more than fit six milestones. All verified
unbuilt on 2026-05-31.

- **C1. Cross-provider failover** — M3 shipped retry/backoff+timeout only
  (`AI_PROVIDER_MAX_RETRIES`/`_TIMEOUT_SECONDS` via `_config.client_kwargs`); a
  hard provider failure still ends the run, no fallback to a secondary provider.
  (Verified: no failover in `threads/tasks.py`/`_stream.py`/`router.py`.) Effort M;
  mid-stream handoff is the hard part — scope to "fail before first token →
  retry on secondary".
- **C2. Observer response-cache / prompt-dedup** — cost lever for repeated
  near-identical observer fires (distinct from Claude input caching, which
  exists). (Verified: none in `apps/observer/`.) Effort M.
- **C3. News quality** — clustering / sentiment / corporate actions
  (splits/dividends — a split reads as a −66% crash to a naive price diff).
  (Verified: none in `market/services/news.py`.) Effort M.
- **C4. Pre-trade decision template** — bind required invalidation/rationale to
  thesis creation (ThesisForm fields still optional). Effort S–M.
- **C5. Watchlist-driven intelligence** — "what changed since I last looked at
  $X" + per-watchlist auto-observe. (Verified: none in `WatchlistDetail`.) Effort M.
- **C6. Scorecard drill-down** — calibration buckets → underlying theses
  (aggregate-only today; data is one query away). Effort S–M.
- **C7. Image offload from Postgres** — M3 age-prunes rows but
  `SnapshotImage.data` is still a `BinaryField` bloating every `pg_dump`. Offload
  bytes to `/data/images/` (the `app_data:/data` volume already mounts). Effort M;
  touches `serve_image`, capture, serializer, backup story. OFF-SPEC-adjacent.

---

## Recommended next milestone — "M7: Eval-driven calibration loop" — ✅ BUILT (local)

The one thread where deferred pieces compound into a real capability (makes the
AI not just measurable but self-correcting — M6's whole thesis):

**B3 (persist EvalRun) → schedule the harness → A3 (feed measured calibration
into the coach prompt) → B1 (predicted_confidence) → B2 (cap pre-flight).**

All backend, ~M effort, builds directly on shipped M6. **Implemented 2026-05-31**
on `feat/m7-eval-calibration-loop` (7 commits, local only — not pushed). The
schedule step landed as an **opt-in** beat task (`AIEVAL_SCHEDULED_ENABLED`,
default OFF) because `run_structured` has no `MOCK_EXTERNAL` short-circuit, so an
always-on schedule would hit the real model. Everything else in Tier C remains
independent — cherry-pick by appetite.

## Execution notes for whoever picks this up
- Branch per unit off `origin/main` (repo is `dan-wiseman94/ai-market-dashboard`;
  local dir is `/home/dan/ai-dashboard`). Push as dan-wiseman94:
  `env -u GITHUB_TOKEN git push` (GITHUB_TOKEN defaults to the wrong identity).
  Pre-push test hook can error spuriously — `--no-verify` is fine when suites
  pass locally.
- TDD via subagent-driven dev; run implementer→review subagents **sequentially**
  (concurrent reviewers misfire on uncommitted SHAs).
- `run_structured` has **no mock-mode short-circuit** → patch it directly in tests.
- Coach upgrades (semantic recall, lessons block, coach-on-triggers) already
  shipped in M1 — do NOT rebuild them.
- After any frontend re-theme, visual e2e baselines need `make e2e-visual-update`.
- See the memory note `improvement-program-2026-05-30` for the full merge history
  + the post-merge-audit lesson (parallel branches touching INSTALLED_APPS /
  urls.py / a shared model's migrations break at the merge seam, not per-branch).
