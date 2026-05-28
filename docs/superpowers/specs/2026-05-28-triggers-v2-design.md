# Triggers v2 — technical-indicator leaves + thesis price-guards — design

**Date:** 2026-05-28
**Status:** Approved (pending spec review)
**Topic:** Two additions to the event-trigger subsystem. **Part A:** technical-indicator condition leaves (RSI, SMA-cross, ATR, distance-from-52w, gap) computed off OHLC across all timeframes — turning Triggers into a self-explaining scanner. **Part B:** auto-generated *thesis price-guards* — when an open thesis opts in, its target/invalidation prices become a live crossing trigger that fires the existing capture+AI pipeline. Spec 2 of a three-spec batch (Snapshot Intelligence → Triggers v2 → Semantic Recall).

## Problem

**Part A.** The trigger DSL (`apps/triggers/dsl.py`) supports `price, pct_change, volume_z, vix, position_pl, position_pl_pct, days_to_earnings`. It cannot express the most common retail setups — "RSI < 30," "50/200 cross," "within 2% of the 52-week high," "gapped up >3%." Today that needs an external scanner. Yet the dashboard already stores OHLC (`apps/market.OHLCBar`) and, uniquely, every trigger firing routes into an AI observation — so a technical scanner here *explains itself*.

**Part B.** A thesis records `target_price` / `invalidation_price` (`apps/thesis/models.py:34-35`), but those prices are **passive** — read once a day in the briefing and in the post-mortem prompt, and never watched in real time. You can write "I'm wrong if AAPL closes below 220" and the system will never tell you when it happens. The trigger subsystem already does real-time price-crossing → snapshot → AI; the gap is purely the *link* from a thesis to a generated trigger.

Both parts lean on a clean existing seam: the evaluator (`apps/triggers/evaluator.py`) is **pure and metric-agnostic** — it reads `metrics[key]` and `_prior:key` and applies ops/`all`/`any`/`not`. New metrics mean teaching `leaf_key()` new key shapes and computing values in two places (live `metrics.py`, replay `backtest.py`) via one shared module; the AND/OR/NOT/crossing logic is untouched.

## Non-goals (YAGNI)

- **No new operator for crosses.** A 50/200 golden cross is modeled as `sma_spread_pct crosses_above 0`, reusing the existing crossing op.
- **No intraday-anchored 52-week / gap.** `dist_from_52w_high/low` and `gap_pct` are daily-anchored (no `window` — implicitly daily); a "52-week high" on 1m bars is meaningless.
- **No auto-disable-guard-after-first-fire** in v2 — guards use a long default cooldown instead (a one-shot-on-hit refinement can come later).
- **No indicator leaves in the snapshot/observer payload** — Part A is trigger-evaluation only.
- **No per-contract option-greek triggers.**
- **No change to the fire pipeline** — guards and technical triggers fire through the existing `triggers.tasks` path (capture + thread + `run_ai_on_message`).

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Indicator params | New optional `params` object on the leaf (extends `LEAF_KEYS`) | RSI/SMA/ATR need a length/period; overloading `window` (a bar timeframe) would conflate two concepts |
| SMA cross | `sma_spread_pct = (sma_fast − sma_slow)/sma_slow` + existing crossing ops vs `0` | Zero new evaluator logic; reuses prior-value crossing machinery |
| Timeframe scope | Multi-timeframe (1m–1d); 52w/gap daily-anchored | User-selected full power; daily-only indicators take **no** `window` (implicitly daily) |
| Live OHLC source | Fetch via `apps/market` OHLC service, Redis-cached per `(ticker, timeframe)`, TTL scaled to window | Correct coverage for any watched ticker; cache keeps the ~10s beat cheap (daily bars barely move intraday) |
| Computation home | One shared pure `apps/triggers/indicators.py` | Live `metrics.py` and replay `backtest.py` compute the DSL one way |
| Backtest crossing | Populate `_prior:<key>` from the previous bar | Crossing ops currently silently never fire in backtest; this makes technical leaves genuinely backtestable |
| Thesis guard opt-in | `Thesis.guard_enabled` default **False** | Each fire costs an AI run; opt-in respects the cost guardrail |
| Guard shape | One `EventTrigger` per thesis with an `{any:[…]}` of target+invalidation crossings | Single row + single cooldown; the AI observation explains which bound hit |
| Guard lifecycle | Explicit `sync_thesis_guard(thesis)` (no signals) | Matches the observer `sync_periodic_task` convention |

## Architecture

```
PART A — technical leaves
  EventTrigger.condition  {metric:"rsi", ticker, window, op, value, params:{period:14}}
        │  dsl.validate_condition (params validated per-metric)
        ▼
  triggers.evaluate_triggers (beat ~10s)
        ├─ metrics.build_snapshot(triggers):
        │     _ohlc_history(ticker, timeframe)  ── Redis-cached ──▶ apps.market OHLC service
        │     indicators.rsi/sma_spread_pct/atr_pct/dist_*/gap_pct(bars + live quote)
        │     leaf_key → "rsi:NVDA:1d:14"  (+ "_prior:…" for crossing ops, cached in Redis)
        ▼
  evaluator.evaluate(condition, metrics)  ── unchanged ──▶ (matched, matched_values)
        ▼
  existing fire path: capture snapshot → Thread → run_ai_on_message

  backtest.backtest(condition, start, end, timeframe):
        rolling close/high/low arrays per ticker → indicators.* per bar
        + _prior:<key> from previous bar  → evaluator.evaluate → matches[]

PART B — thesis guards
  Thesis(guard_enabled=True, target/invalidation set, status=open)
        │  ThesisViewSet create/update/close → sync_thesis_guard(thesis)
        ▼
  build_guard_condition(thesis) → {any:[{price crosses_above target}, {price crosses_below invalidation}]}
        ▼
  get_or_create EventTrigger(source_thesis=thesis, profile=thesis.profile or first, long cooldown)
        ▼
  fires through the existing trigger pipeline; matched_values shows which bound crossed
  (thesis closed/invalidated/guard_enabled=False → guard disabled/removed)
```

## Part A — technical-indicator leaves

### A1. DSL — `apps/triggers/dsl.py`

```python
INDICATOR_METRICS = {"rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct",
                     "dist_from_52w_high", "dist_from_52w_low", "gap_pct"}
DAILY_ONLY_METRICS = {"dist_from_52w_high", "dist_from_52w_low", "gap_pct"}
VALID_METRICS |= INDICATOR_METRICS
LEAF_KEYS |= {"params"}
TICKER_REQUIRED |= INDICATOR_METRICS
WINDOW_REQUIRED |= (INDICATOR_METRICS - DAILY_ONLY_METRICS)   # multi-tf indicators need a bar timeframe

PARAMS_SPEC = {
    "rsi":             {"period": (int, 14, 2, 100)},        # (type, default, min, max)
    "atr_pct":         {"period": (int, 14, 2, 100)},
    "dist_from_sma_pct": {"period": (int, 50, 2, 400)},
    "sma_spread_pct":  {"fast": (int, 50, 2, 400), "slow": (int, 200, 3, 600)},
}
```

`validate_condition` additions (same path-precise `ValidationError` style):
- `params` must be a dict when present; reject unknown param keys; coerce/validate each declared param's type + range; default-fill omitted params; for `sma_spread_pct` require `fast < slow`.
- `DAILY_ONLY_METRICS` take **no** `window` (implicitly daily): they are excluded from `WINDOW_REQUIRED`, so the existing "window not allowed" rule (`dsl.py:80`) already enforces absence. They evaluate on daily bars and their `leaf_key` omits the window.
- `tickers_in_condition` already collects `ticker` from any leaf — unchanged.

### A2. Indicators — `apps/triggers/indicators.py` (new, pure, no I/O)

```python
def rsi(closes: list[float], period: int) -> float | None        # Wilder's; None if < period+1 bars
def sma(values: list[float], period: int) -> float | None
def sma_spread_pct(closes: list[float], fast: int, slow: int) -> float | None   # (smaF-smaS)/smaS
def atr_pct(highs, lows, closes, period, last: float) -> float | None           # ATR/last
def dist_from_high(highs: list[float], last: float) -> float | None             # (last-max)/max  (≤0)
def dist_from_low(lows: list[float], last: float) -> float | None               # (last-min)/min  (≥0)
def gap_pct(today_open: float, prev_close: float) -> float | None               # (open-prevC)/prevC
```

Every function returns `None` on insufficient/degenerate input (the evaluator already treats `None` as a non-match). Heavily `parametrize`d against known fixtures.

### A3. Evaluator — `apps/triggers/evaluator.py`

Only `leaf_key()` changes — add deterministic key shapes (period baked in so different lengths are distinct metric/cache entries):

```
rsi:<T>:<win>:<period>      sma_spread_pct:<T>:<win>:<fast>:<slow>     atr_pct:<T>:<win>:<period>
dist_from_sma_pct:<T>:<win>:<period>     dist_from_52w_high:<T>     dist_from_52w_low:<T>     gap_pct:<T>
```

`_eval_leaf`, crossing logic, `all/any/not` — **unchanged**.

### A4. Live metrics — `apps/triggers/metrics.py`

- **OHLC provider:** `_ohlc_history(ticker, timeframe) -> OHLCSeries` (closes/highs/lows/opens). Redis-cached key `trigger:ohlc:<ticker>:<tf>`; on miss, fetch via the existing `apps.market` OHLC service, requesting the **max lookback** needed across that ticker's leaves at that timeframe (`max(period, slow, 252-for-52w) + buffer`). TTL scaled to the window (`_WINDOW_SECONDS[tf]`, capped — daily ≈ 1h). The in-progress value uses the live quote `last` appended to the closed bars.
- **build_snapshot:** group indicator leaves by `(ticker, timeframe)` (daily-only leaves with no window are grouped under the `1d` timeframe); fetch history once per group; compute each leaf via `indicators.*`; write `snapshot[leaf_key]`. For crossing ops, cache the computed value to Redis and read `_prior:<key>` exactly as `_record_last_metric` does for `price` today.
- Failures degrade to `None` (logged), never raise — consistent with the existing quote/position handling.

### A5. Backtest — `apps/triggers/backtest.py`

- Maintain rolling `closes/highs/lows/opens` per ticker as bars are walked in `ts` order; compute indicator values per bar via `indicators.*` and write them into the per-bar `snapshot` under `leaf_key`.
- **Crossing fix:** keep a `prev_values: dict[str, float|None]` across bars and set `snapshot[f"_prior:{key}"] = prev_values.get(key)` before `evaluate`, then update `prev_values`. This makes `crosses_above/below` (price, sma_spread_pct, …) actually evaluate in replay — today they never match. Existing `price`/`pct_change` handling preserved.
- Daily-only metrics already align with the default `timeframe="1d"`; reject indicator backtests at a non-matching timeframe with a clear error if 52w/gap leaves are present at a non-`1d` timeframe.

## Part B — thesis price-guards

### B1. Models (two small migrations)

- `apps/thesis/models.py`: `Thesis.guard_enabled = models.BooleanField(default=False)`.
- `apps/triggers/models.py`: `EventTrigger.source_thesis = models.ForeignKey("thesis.Thesis", null=True, blank=True, on_delete=models.CASCADE, related_name="guard_triggers")`. Presence of `source_thesis` marks a trigger as thesis-managed.

### B2. Generation + lifecycle — `apps/triggers/services/thesis_guard.py` (new)

```python
def build_guard_condition(thesis) -> dict | None:
    """One {any:[...]} of price crossings from the thesis prices+direction. None if no prices."""
    # bullish:  price crosses_above target ; price crosses_below invalidation
    # bearish:  price crosses_below target ; price crosses_above invalidation
    # neutral:  range break on either bound (both must be set)

def sync_thesis_guard(thesis) -> EventTrigger | None:
    """Idempotent. Create/update the linked guard when guard_enabled & open & has prices;
    disable/remove it otherwise. Profile = thesis.profile or TradingProfile.objects.first();
    returns None (with a logged reason) when no profile exists."""
```

- Condition only includes the bound(s) whose price is set; built via the same `price`/`crosses_*` leaves, so it passes `validate_condition`.
- Guard `EventTrigger`: `name=f"Guard: {thesis.title}"[:100]`, `source_thesis=thesis`, `enabled=True`, a long default `cooldown_seconds` (e.g. 6h) so a hit doesn't spam. `get_or_create` keyed on `source_thesis`; update `condition`/`enabled` on change.
- **Wiring (explicit, no signals):** call `sync_thesis_guard(thesis)` from `ThesisViewSet.perform_create`, `perform_update`, and the thesis close action — mirroring `ObserverScheduleViewSet`'s explicit `sync_periodic_task`. A guard whose thesis is deleted is removed by the `CASCADE`.

### B3. Firing

Guards fire through the **unchanged** `triggers.tasks` pipeline (cooldown guard, snapshot capture, thread, `run_ai_on_message`, cost caps). `TriggerFiring.matched_values` records which leaf (`price:<T>` with its `_prior`) crossed, so the AI prompt and the firing row both show whether target or invalidation was hit.

## Frontend

- **Trigger editor** (`TriggerEditorPage` / condition builder): add the new metrics to the leaf metric dropdown; render a small **params sub-form** (period; fast/slow) shown only for indicator metrics; a friendly **"SMA cross"** preset that emits `sma_spread_pct crosses_above/below 0`. `BacktestPanel` already replays the condition — now meaningful for technical + crossing leaves.
- **Thesis detail** (`ThesisDetailPage`): a **"Price guard"** toggle bound to `guard_enabled` (disabled with a tooltip when target & invalidation are both empty, or no profile exists). Show the linked guard's status/last-fired.
- **Triggers list:** guard (`source_thesis != null`) rows render with a "managed by thesis" badge + link back to the thesis; their condition is read-only in the editor.
- API additions: thesis serializer exposes `guard_enabled` (writable) + a read-only `guard_trigger_id`; trigger serializer exposes read-only `source_thesis_id`.

## Testing

- **`test_indicators.py`** — parametrized RSI/SMA/ATR/52w/gap against known fixtures; insufficient-bars and degenerate (flat/zero) → `None`.
- **`test_dsl.py`** (extend) — `params` validation (type/range/unknown-key/`fast<slow`); daily-only metrics require `window:"1d"`; defaults filled.
- **`test_evaluator.py`** (extend) — new `leaf_key` shapes.
- **`test_metrics.py`** — `_ohlc_history` cache hit/miss + TTL; indicator wiring with a mocked OHLC service + quote; crossing prior cached/read; failures → `None`, never raise.
- **`test_backtest.py`** (extend) — indicators per bar; **crossing ops now match** over fixture bars; daily-only timeframe guard.
- **`test_thesis_guard.py`** — `build_guard_condition` per direction (+ missing prices → None); `sync_thesis_guard` enable/disable/close/price-change/no-profile idempotency; guard validates against the DSL.
- **Frontend (`vitest`)** — editor params sub-form + SMA-cross preset; thesis guard toggle states.
- **E2E (`api`/`ws`)** — a guard trigger fires under `MOCK_EXTERNAL` and lands a firing + observation.

## Ops & migrations

- `apps/thesis/migrations/`: `AddField Thesis.guard_enabled` (default False — reversible).
- `apps/triggers/migrations/`: `AddField EventTrigger.source_thesis` (nullable FK, `CASCADE` — reversible).
- DSL/evaluator/metrics/backtest/indicators are code-only (no migration).
- **`docker compose restart worker beat`** after deploy — `metrics.py`/`evaluator.py` run inside the worker/beat, which don't hot-reload. No new task or beat entry (reuses `evaluate_triggers` + `run_ai_on_message`).
- No new dependency (indicators are stdlib `statistics`/math; OHLC via existing `apps.market`). No new credential.

## Implementation order (for the plan)

1. `apps/triggers/indicators.py` (pure functions) + `test_indicators.py`.
2. DSL: `params` + new metrics + daily-only validation (`dsl.py`) + `leaf_key` shapes (`evaluator.py`) + tests.
3. Backtest: rolling windows + indicators + `_prior:` crossing fix + tests (independent of live).
4. Live: `_ohlc_history` cache + `build_snapshot` indicator branches + tests.
5. Part B models (`Thesis.guard_enabled`, `EventTrigger.source_thesis`) + migrations.
6. `thesis_guard.py` (`build_guard_condition`, `sync_thesis_guard`) + ViewSet wiring + tests.
7. Frontend: trigger-editor params/preset, thesis guard toggle, managed-trigger badge, serializer fields, vitest.
8. E2E guard-fire check.

Steps 1–4 (Part A) and 5–6 (Part B) are independent; step 3 is independent of 4. Step 7 depends on 2 (metrics) + 6 (guard fields).
