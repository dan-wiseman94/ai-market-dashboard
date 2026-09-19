# Macro-Desk Coverage — Follow-On Work & Learnings

**Written 2026-09-19**, before executing the 17-task plan
(`docs/superpowers/plans/2026-09-19-snapshot-macro-desk-coverage.md`, spec
`…/specs/2026-09-19-snapshot-macro-desk-coverage-design.md`). Everything here is work
that intentionally does NOT happen in that plan, plus what the audit → spec → verification
cycle established that a future session should not have to re-derive.

## 1. Gated on the TradingView MCP branch merging (Workstream E)

`worktree-tradingview-mcp` (spec `…/specs/2026-09-19-tradingview-mcp-design.md`) was in
execution when this was written. Once it merges, a small follow-up plan covers:

- **Symbol-map rows** in `apps/market/services/tradingview.py` — `$`-prefixed into
  `INDEX_SYMBOLS`, `/`-prefixed into `FUTURE_SYMBOLS`: `$VVIX→TVC:VVIX`,
  `$DXY→TVC:DXY` (plus a `$DXY` alias in `symbols.INDEX_ALIASES`),
  `$IRX/$FVX/$TYX→TVC:US03MY/US05Y/US30Y`, `$US2Y→TVC:US02Y` (new tenor),
  `$SKEW→CBOE:SKEW`, `/ZQ→CBOT:ZQ1!`. Live-verify each row by quoting it through
  `tv_get_symbol_data_batch` — **including units**, not just resolution.
- **The yields unit contract (was a review BLOCKER)** — `yields.py` divides every quote
  by 10 (CBOE `$`-yield-indices quote yield×10), but TradingView's `US02Y/US03MY/US05Y/US30Y`
  publish yield **in percent**. A flat ÷10 silently renders those tenors 10× low and passes
  the `last > 0` gate. `YIELD_INDICES` must become `ticker → (tenor, divisor)` before any
  TV tenor row lands.
- **Scoping reality for `$US2Y` / the live 2s10s** — the fallback chain engages only on
  `SchwabNotConnectedError`, and the locked TV rule is "the first configured provider
  answers, even if it answers empty". Schwab has no 2Y yield index, so on a
  Schwab-connected install the 2Y slot still never renders. Optional fix (the one
  deliberate per-symbol provider merge): `live_yields` consults the TV provider directly
  for Schwab-less tenors, gated on `tradingview.is_connected()`.
- **Optional** — `/VX2` continuous second month (`CFE:VX2!`) so the Schwab-less contango
  read survives (today TV fallback yields spot + continuous front only; dated `/VXU26`-style
  legs map to `None`); a "Rec trend" line in the fundamentals render via the TV forecasts
  normalizer (analyst revisions are otherwise on-demand-only via `tv_get_forecasts` /
  `tv_get_technicals_rating`); a `/ZQ` strip render for the market-implied Fed path.
- **Post-merge doc touchpoints** — README's free-data-sources bullet, the "on a free key
  the curated seed is the effective macro source" sentence (TV retires the seed as the live
  macro source when connected), and the architecture diagram's provider box; CLAUDE.md's
  "free fallback providers can't quote CFE futures → spot-only" weakens to
  "spot + continuous front month via TradingView; spot-only otherwise". TradingView is a
  **paid-plan OAuth source** — never list it under "free data sources".

## 2. Coordination before/at the branch merge

- **Uncommitted doc-sync on main (MERGE HAZARD).** The 2026-09-19 capability doc sync
  (README.md, FEATURES.md, CLAUDE.md, docs/marketing-copy.md) sits **uncommitted in the
  main checkout's working tree**. Plan Task 17 edits the same files on
  `worktree-snapshot-macro-desk`, which branched WITHOUT those edits. Commit the doc-sync
  on main before merging the branch, and expect textual conflicts in those four files at
  merge time — resolve by keeping both: the doc-sync's corrected wording (e.g. EDGAR is
  10-K/10-Q/8-K today) updated for what the branch shipped (Form 4 becomes true again).
- **`apps/secrets/data_sources.py`** is the one file both this branch and the TV branch
  touch (different regions; trivial rebase, but whoever merges second rebases).
- **Two other unmerged branches predate all this** (unrelated but open):
  `fix/snapshot-observation-data-quality` (PR #134) and `feat/new-user-onboarding`
  (spec+plan committed, unexecuted).

## 3. Dispositioned in the spec (§8) — revisit only with new leverage

- Breadth internals without Schwab (TV maps `$ADVN/$DECN/$TICK/$TRIN` to `None`; no free
  source) — the computed `breadth_stats` metrics are the mitigation.
- Real per-ETF fund flows — no free source exists; `flowlite` is an honest volume proxy.
  A paid flow API would follow the `fred.py` keyed-fetcher pattern.
- Multi-underlying / SPX-index chains and gamma — chain stays single-underlying (SPY as
  the index proxy).
- Fed content *interpretation* — the `fed` section delivers headlines/links; reading
  statements is run-time AI/tool work.
- Diff-mode observers bypass `serialize_for_ai` entirely — every render improvement is
  invisible on that path.
- Chart-image base64 and Claude news `search_result` blocks ride OUTSIDE
  `prune_to_budget`'s token accounting (news is delivered twice on Claude runs).
- The 40k unknown-model payload default (`catalog.py`) — binds only for uncataloged Local
  models; prune order handles it.
- Marketaux per-ticker sentiment stays unstored; news 24h/15 caps stay — revisit after the
  TV-first news fallback and the schedules includes-editor bake.

## 4. Learnings worth keeping (established this cycle, evidence in the audit/spec)

**Root causes of the coverage gaps (audit: 0 of 16 fully covered / 11 partial / 5 missing):**
- `TradingProfile.DEFAULT_INCLUDES` was `['quotes','positions','breadth']` AND
  `save()` seeds only an *empty* `default_includes` — constant changes never reach
  existing profiles without a data migration.
- The FE offered 5 of 15 section kinds (`profiles/types.ts` `SECTION_OPTIONS`), and
  SchedulesPage never set `ObserverSchedule.default_includes` — "opt-in" was unreachable
  from the UI.
- The **computed-but-discarded** pattern recurs: per-strike GEX built then thrown away,
  sector 1d %-change fetched then dropped, `eps_actual`/`rev_est` captured but unrendered,
  UUP ingested nightly but never quoted into a payload, Marketaux sentiment fetched and
  not stored. When auditing coverage, grep for what services *compute*, not just what
  sections *exist*.

**Cost & tokens:**
- Everything-on renders ≈25–40k tokens vs catalog budgets (Claude 150k, gpt-5 300k) —
  token budget was never the constraint; delivery was.
- A 10-min Opus observer at ~30k-token prompts costs ≈$17.5/day input on a market-hours
  cron, ≈$65/day 24/7 ($15/MTok). An earlier $6.5/day figure was wrong by 3–10× and was
  quoted when the rich-defaults decision was made; the decision was reaffirmed on the
  corrected number. Live-quote lines also make byte-identical prompts rare, cutting
  `OBSERVER_RESPONSE_CACHE_ENABLED` hits. Per-schedule `default_includes` is the lever.

**Fallback/provider semantics traps (each cost a spec correction):**
- Alpaca's quote fallback is one whole-batch request — one rejected symbol (`/ES`) blanks
  the entire batch. Futures/index rows need their own `fetch_quotes` call.
- Tiingo/Polygon treat a "bars" count as a **calendar-day lookback** (260 → ~178 bars),
  and `polygon.py` hardcoded aggregates `limit: 120`.
- `OHLCBar` is retention-pruned at `AI_RETENTION_OHLC_DAYS` (default 400 calendar days
  ≈ 275 trading bars) — 52-week metrics need `retention_ohlc_days ≥ ~380` and honest
  real-window labels.
- `fetch_filings` applies ONE shared newest-first `limit` across all forms — adding
  high-frequency Form 4 to the shared tuple evicts 10-K/10-Q/8-K; fetch Form 4 separately.
- EDGAR "Form 4 insider trades" was advertised (`data_sources.py`) but never fetched —
  doc-vs-code drift found by auditing claims against call sites.

**Gates & environment:**
- First backend XML parse (`fed.py`) trips ruff S314 AND the **blocking** `semgrep ci`
  registry packs. Resolution: reject `<!DOCTYPE`/`<!ENTITY` outright + 512 KB cap
  (defusedxml's forbid_dtd/forbid_entities semantics) — chosen over adding defusedxml
  because the worktree test harness reuses baked images and cannot install packages.
- Worktree execution: untracked `compose.worktree.yaml` overlay + own compose project
  (`-p macrodesk`), `LEFTHOOK=0` for commits, and the session git guard refuses `git -C`
  into the shared checkout — exit/re-enter the worktree to touch main.
- The TV branch's plan (lines 15–16) is the canonical reference for the `$DC run` command
  forms (pytest / ruff `-w /app --entrypoint ""` / spectacular / vitest).

**Process:**
- Adversarial verification of an already-"verified" spec surfaced 22 findings including
  one genuine blocker (the yields unit contract) and the 3–10× cost error — worth the
  pass every time a spec commits to numbers or cross-provider behavior.
