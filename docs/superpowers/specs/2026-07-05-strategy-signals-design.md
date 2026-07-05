# Strategy Signals — design

**Date:** 2026-07-05
**Status:** approved
**Scope:** M16 — four new signal families routed by trading-strategy tags into snapshot payloads, the trigger DSL, a dashboard signals panel, and regime/coverage inputs.

## 1. Problem

The dashboard computes a number of market signals, but they are trapped per surface: option-chain analytics (put/call, GEX, IV skew, term structure) exist only as render-time markdown inside `apps/snapshots/serializer.py`; relative strength and sector rotation reach only the breadth section; the trigger DSL, the UI, and the strategy app each see a different (smaller) signal set. Whole strategy families have no representation at all — mean-reversion statistics, deep momentum, IV rank, short interest, sentiment. And nothing links a `TradingProfile`'s trading style to which signals it sees: every capture gets the same sections regardless of whether the profile is a momentum trader or an options-income seller.

## 2. Goals / non-goals

**Goals**

- One signal engine — a single source of truth for signal math, consumed by all surfaces.
- Four families: momentum/trend, mean-reversion, volatility/options-flow, positioning/sentiment.
- Strategy routing: profiles declare `strategy_tags`; the tagged families drive what the AI sees and what the UI emphasizes.
- Surfaces: snapshot payload (AI), trigger DSL metrics, an analytics signals panel, regime/coverage inputs.
- Data: existing providers plus new free/keyless sources (FINRA); graceful degradation everywhere.

**Non-goals**

- No broker write path, no scanner/screener product, no paid data subscriptions.
- No materialized signal values (signals are computed on demand; only *input history* is persisted).
- No new regime axis, no briefing changes, no desk detectors in this milestone.

## 3. Architecture

New package `backend/apps/market/services/signals/`:

```
signals/
  engine.py       # compute_signals(ticker, families=None, *, benchmark="$SPX")
  momentum.py     # pure family math
  reversion.py
  volatility.py
  positioning.py
  bundles.py      # STRATEGY_TAGS vocabulary; tag -> family map; suggested trigger presets
```

- `compute_signals` returns `{family: {signal_name: value | None}}`. Each family module exposes `compute(ticker, ctx) -> dict`; a signal with insufficient inputs is `None` — never invented (leaderboard convention).
- Primitive indicator math (MACD, ADX, Bollinger %B, HV, z-score) is added to the existing single source `apps/market/services/indicator.py::compute`, which the trigger DSL, backtest, and regime already share via `apps/observer/triggers/indicators.py::indicator_value`. The engine consumes the same chain — live triggers, backtest replay, and the panel cannot diverge.
- Results are Redis-cached per `(ticker, family)` with kinds registered in `apps/market/cache.py::_TTL` (intraday-sensitive families ~120s; daily-derived ~3600s). Unregistered kinds silently default to 30s — every new kind is registered.
- The package lives in `apps.market` (data access, import-linter allowances, siblings `intel.py` / `option_analytics.py` / `returns.py`). Other apps import it directly, like `returns.py`.
- `.gitignore` has no `signals` pattern (checked — the `coverage/` collision does not recur).

## 4. Strategy routing

- `TradingProfile.strategy_tags` — JSONField list, default `[]`, validated in `TradingProfileSerializer` against `bundles.STRATEGY_TAGS = {"momentum", "mean_reversion", "vol_options", "positioning"}`. The serializer `Meta.fields` list is explicit — the field is appended there (the model-only `skills` field is standing proof that omission is silent).
- Routing point is the **section fetcher**, not includes resolution. One new snapshot section kind `signals` (7 chars; `SnapshotSection.kind` is varchar(16)). The fetcher loads `Snapshot.objects.get(pk=snapshot_id).profile.strategy_tags` and computes only the tagged families. **Empty tags → all four families** (neutral default for an observational tool; the section itself is opt-in via `default_includes`).
- Because routing lives in the fetcher, the three independent includes-resolution call sites (`snapshots/views.py:79`, `observer/services/run.py:92`, `observer/triggers/tasks.py:131`) and the briefing's hard-coded list are untouched; trigger- and observer-fired snapshots pick the section up through the existing `default_includes` flow. No duplicate-kind risk (the `(snapshot, kind)` unique constraint aborts a capture on duplicated includes).

## 5. Data layer — input history

Persist inputs that need lookback; compute signals on demand.

### 5.1 Deeper daily bars

- `market.ingest_daily_bars` requests `bars=300` (was 60) — covers 252-session lookbacks; universe unchanged.
- Fallback fixes that ride along (today a deep request silently under-delivers):
  - `fallback.alt_bars` passes a **bar count** into Tiingo/Polygon **calendar-day** params — convert `days = ceil(bars * 1.5)`.
  - `polygon.fetch_daily_bars` hardcodes `limit: 120` — parameterize.
- `retention_ohlc_days` default 400 already fits 252 sessions.

### 5.2 `IVDaily` (new model, apps.market)

One row per `(ticker, date)` of compact scalars — not chain JSONB: `atm_iv`, `term_slope`, `put_call_vol`, `put_call_oi`, `gex_total`, `flip_strike`, `hv_20`. Written by new beat task `market.ingest_iv_summary` (nightly 20:45 UTC, before the bar ingest) looping watchlist tickers with chain access (Schwab/Tradier); no chain source → no row, silent. Distilled from `chain_analytics()` + stored closes. Retention knob `retention_iv_days` default 430. IV rank/percentile report `None` below 60 rows and carry `n` (row count) so a young rank is not mistaken for a full-year rank.

### 5.3 `ShortInterestRecord` (new model) + FINRA client

FINRA publishes short interest twice monthly, keyless. New `services/finra.py` follows the keyless-client template: `is_mock_mode()` canned fixture, never raises, `safe_err` logging. Rows per `(ticker, settlement_date)`: `shares_short`, `avg_daily_volume`, `days_to_cover`. Beat task `market.refresh_short_interest` daily 10:00 UTC — no-op unless a new report date appeared. FINRA gets a `DATA_SOURCES` catalog entry (`auth: "none"`) and a `_probe_finra` for the settings Test button. Retention knob `retention_short_interest_days` default 430.

### 5.4 Riders

- `NewsItem.sentiment` (nullable float) — Marketaux already parses per-ticker sentiment and drops it; persist when present. Finnhub/Tiingo news never set it; all readers null-safe.
- `BreadthDaily` (new model) — one row per session: `advn_close`, `decn_close`, `net_ad`. Captured inside `ingest_daily_bars` (no new task). Schwab-only symbols; without Schwab no rows are written and A/D signals are `None`. Retention knob `retention_breadth_days` default 800 (rows are tiny).
- Insider transactions + analyst recommendation trends: fetched live from Finnhub free endpoints with a 24h Redis cache (the `fetch_fundamentals` template — never raises, returns `{}`). Not persisted: the recommendation endpoint returns its own monthly history.

New models get `core.prune_retention` entries with `runtime_config()` knobs. Both beat tasks are registered in `apps/core/scheduled_tasks.py` in the same change (drift gate), named with the owning-app `market.` prefix. Deploy note: worker/beat need a restart to see new task modules.

## 6. Signal inventory

Per ticker unless noted; every value `None` on missing inputs.

| Family | Signals |
|---|---|
| `momentum` | `macd_hist` (12/26/9), `adx` (14), `rs_vs_spx` (63d; `intel.RS_WINDOWS` extended with 63/126/252), `rs_vs_sector` (sector-ETF map from `CompanyFundamentals.sector` → `SECTOR_ETFS`), `ma_alignment` (20>50>200 state), `mom_12_1` (12-month return excluding the last month) |
| `mean_reversion` | `zscore_20d`, `bollinger_pct_b` (20, 2σ), `rsi2`, `dist_vwap_pct` (session VWAP from intraday bars; `None` off-hours/no intraday), `consec_days` (signed run length) |
| `vol_options` | `iv_rank_252`, `iv_percentile_252` (IVDaily, n-labeled), `hv_20`, `hv_iv_spread`, `term_slope`, `put_call_vol`, `put_call_oi`, `gex_total`, `dist_to_flip_pct` |
| `positioning` | `si_days_to_cover`, `si_change_pct` (vs prior report), `insider_net_90d` (Finnhub buys−sells), `analyst_rating_avg` (1–5, strong sell → strong buy, weighted over Finnhub recommendation counts), `analyst_delta_30d`, `news_sentiment_7d`, market-wide `ad_line_slope_20d` (BreadthDaily; lives under the payload's `_market` key, not per-ticker) |

The chain-derived volatility signals read the same `chain_analytics()` the serializer uses; the serializer's chain section keeps rendering exactly as today.

## 7. Trigger DSL — eight curated metrics

Each DSL metric touches ~8 places (dsl registry sets, `evaluator.leaf_key` branch, `metrics._record_leaf` recorder, crossing priors, `describe`, three hand-synced FE lists, per-family tests), so only alert-worthy signals are admitted:

- **Backtestable** (OHLC-derived; added to the shared `indicator_value()` dispatch so live and backtest cannot diverge): `macd_hist`, `adx`, `zscore`, `bollinger_pct_b`. `PARAMS_SPEC` entries with int params (`zscore`/`bollinger_pct_b` take `period`, default 20 — the parameterized generalization of the engine's fixed `zscore_20d`/`bollinger_pct_b` defaults); matching `_INDICATOR_KEY_PARAMS` entries (the params-sync trap); `_bars_needed` extended for their lookbacks (≤500-bar cap respected).
- **Live-only** (absent from backtest per-bar snapshots — the established precedent): `iv_rank` (evaluates the engine's `iv_rank_252`), `put_call_vol` (read IVDaily/chain through the engine), `si_days_to_cover`, `news_sentiment` (evaluates `news_sentiment_7d`). All four join `NON_CROSSING_METRICS` (slow-moving values; no `_prior:` plumbing).

Recorder rules (landmine-driven):

- Every recorder catches and logs — an escaping exception permanently disables the user's trigger (`_disable_on_bad_condition`).
- Every new metric gets an explicit `leaf_key()` branch — the fall-through default silently evaluates the metric as `price`.
- Batched inputs follow the `needs_x` guard + per-tick cache-dict pattern; Redis-stateful recorders dedupe per key.

Hygiene fixes in the same milestone: the FE trigger builder is missing five existing backend metrics (`days_to_earnings` + four fundamentals) — sync `Metric` union, `LeafRow` arrays, `describe.ts`; correct the stale "only price/pct_change" claims in `views.py` docstring and `BacktestPanel.tsx`.

Per-tag suggested trigger presets live in `bundles.py` and surface as preset buttons in the builder (the `SMA_CROSS_PRESET` pattern) — e.g. `mean_reversion` suggests `zscore < -2`.

## 8. Surfaces

### 8.1 Snapshot section `signals`

- Fetcher in `_FETCHERS`: computes tagged families for up to 8 watchlist tickers (fundamentals cap precedent); payload `{ticker: {family: {signal: value}}, "_market": {...}}`. The `_market` key is reserved and excluded from primary-ticker derivation.
- `SnapshotSection.KIND_CHOICES` + migration.
- Renderer in `_RENDERERS` + `_title` ("Strategy signals"): compact per-ticker lines, deterministic output (no now-relative text — the observer response cache keys on payload bytes).
- `token_budget._PRUNE_ORDER`: `signals` inserted after `breadth`, before `quotes` — never an un-prunable section.
- `diff.py::_diff_one` branch rendering scalar deltas ("AAPL iv_rank 34→58") — otherwise the section is invisible to diff-mode observers and coverage revisions.
- FE pickers: add `signals` to both `SnapshotSectionPicker.SECTIONS` and profile-form `SECTION_OPTIONS`.

### 8.2 Analytics endpoint + UI

- `GET /api/analytics/signals/?ticker=X` — on-demand DRF view (no Celery; analytics convention), returns families with per-signal `value | null` plus an `insufficient_history` marker and `n` where relevant. Query-budget test (`django_assert_max_num_queries`) like sibling aggregations. `make schema` regen.
- FE: "Strategy Signals" analytics card — ticker input before data (the `UnusualOptionsCard` hand-rolled-shell pattern), signals grouped by family, families matching the selected profile's tags highlighted. `data-testid="analytics-card-signals"`, co-located stories (the storyless ratchet is at its ceiling), vitest component test.
- Watchlist expander: a gated signals query inside the per-ticker expander (`enabled: open` — the `TickerChanges` pattern; no request storm).
- `strategy_tags` edit UI: checkbox set in `ProfileForm` threaded through the four hand-maintained FE spots (`api/profiles.ts` type, `types.ts` Draft + BLANK_DRAFT, `useProfileForm.startEdit`, form control). `pnpm gen:api` runs on the host (container-broken per project memory).

### 8.3 Regime & coverage

- Regime: `gather_inputs` gains `ad_line` (BreadthDaily 20d slope) in its own isolated try/except; `classify_breadth` uses it as fallback when live `$ADVN/$DECN` are absent. **No sixth axis** — the ±2 composite thresholds stay tuned for five.
- Coverage: `_build_prompt` appends a compact signals block for the note's ticker (families per the `profile` already in scope), `_safe`-wrapped to empty on any error — `revise_coverage` keeps its never-raises contract. The block is appended in both diff and full modes.

## 9. Error handling

One philosophy: **absent, never invented; degrade, never raise.**

- Engine: never raises; each signal independently `None`.
- Section fetcher: returns whatever computed; partial payloads are normal; a catastrophic error marks only the section `failed` (existing loop semantics).
- Trigger recorders: swallow + log (an escape disables the trigger).
- Analytics view: nulls with `insufficient_history` reasons; FE renders "—".
- Coverage/regime blocks: `_safe`-wrapped / try-except-isolated.
- Provider clients (FINRA, Finnhub extras): never raise, `safe_err` logging (keys must not reach logs), `is_mock_mode()` fixtures.
- MOCK_EXTERNAL: mock Schwab returns empty candles — e2e signal assertions seed `OHLCBar` rows directly.

## 10. Testing

- **Unit:** pure math per family module (parametrize; Hypothesis bounds for `zscore`/`pct_b` ∈ ranges, HV ≥ 0); `bundles` vocabulary; engine family selection.
- **Trigger DSL:** per-family `test_dsl_<family>.py` + `test_metrics_<family>.py` (the fundamentals template): leaf validation, `leaf_key` shape, recorder resolution with patched fetchers, absent-on-failure, evaluate() end-to-end; `test_backtest_indicators.py` for the four backtestable metrics; crossing tests for indicator metrics.
- **Ingest:** respx tests for FINRA/IV summary tasks; idempotent upserts; retention pruning entries.
- **Snapshots:** serializer render, prune order, diff branch, section capture with failing engine.
- **API:** analytics view contract + N+1 budget; schemathesis picks the endpoint up automatically.
- **FE:** vitest for the signals card, LeafRow params for new metrics, describe wording, profile-form tags round-trip; stories for every new component.
- **Gates touched in-change:** migrations (`make check-migrations`), `scheduled_tasks.py` (+2 beat tasks, drift gate), OpenAPI schema + `schema.d.ts` (drift-gated), coverage floors, no new feature flags.

## 11. Delivery phases

1. **P1 — data layer + engine:** models, migrations, ingest tasks, fallback bar-depth fixes, family math, engine + cache. Independently shippable (nothing consumes it yet).
2. **P2 — snapshot section + strategy_tags:** profile field end-to-end, section kind/fetcher/renderer/prune/diff, FE pickers + profile form.
3. **P3 — trigger DSL:** eight metrics + FE builder sync + hygiene fixes + presets.
4. **P4 — analytics endpoint + signals card + watchlist expander.**
5. **P5 — regime + coverage inputs.**

## 12. Landmines checklist (verify at implementation)

- [ ] Serializer `Meta.fields` includes `strategy_tags` (silent omission otherwise).
- [ ] `leaf_key()` branch per new metric (fall-through evaluates as price).
- [ ] `_INDICATOR_KEY_PARAMS` entries match `PARAMS_SPEC` (key collision otherwise).
- [ ] `signals` in `_PRUNE_ORDER` (un-prunable otherwise) and in `diff.py` (diff-invisible otherwise).
- [ ] Section kind ≤16 chars; no duplicate kinds in any includes list.
- [ ] Cache kinds registered in `_TTL` (30s default hammers free APIs).
- [ ] Beat tasks in `scheduled_tasks.py`, `market.` prefix; worker/beat restarted after deploy.
- [ ] `safe_err` for any provider whose key rides in the URL; FINRA is keyless but follows the template.
- [ ] Renderer deterministic (observer response cache).
- [ ] `revise_coverage` / `gather_inputs` never-raise contracts preserved.
- [ ] Dashboard/analytics defaults are full contract-valid shapes if any rollup section is ever added.
- [ ] New FE components ship with stories (ratchet at ceiling).
