# M16 P3 — Trigger DSL Signal Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit exactly eight curated signal metrics into the trigger DSL — four backtestable indicators (`macd_hist`, `adx`, `zscore`, `bollinger_pct_b`) and four live-only engine reads (`iv_rank`, `put_call_vol`, `si_days_to_cover`, `news_sentiment`) — with full FE builder sync, hygiene fixes for five already-missing metrics, and per-tag trigger presets.

**Architecture:** The trigger DSL is a set-registry validator (`dsl.py`) feeding a pure evaluator (`evaluator.py`) over a flat metrics snapshot built each beat tick (`metrics.py`); OHLC-derived indicator math flows through one shared dispatch (`triggers/indicators.py::indicator_value`, delegating to `apps/market/services/indicator.py`) used identically by the live path and backtest replay, so the two cannot diverge. The four backtestable metrics join the existing `INDICATOR_METRICS` machinery (params, key shapes, crossing priors, backtest replay all come along by set membership plus a dispatch branch); the four live-only metrics get a new recorder that reads the P1 signals engine (`compute_signals`) with a per-tick cache, absent-on-failure semantics, and no crossing support.

**Tech Stack:** Django/DRF, Celery beat tick (`triggers.evaluate_triggers`), Redis (crossing priors + OHLC cache), pytest + fakeredis; React/TypeScript, vitest + @testing-library/react.

**Spec:** docs/superpowers/specs/2026-07-05-strategy-signals-design.md (§7, §12)

**Phase position:** P3 of 5. **Hard dependency: P1 must be merged** (it provides `apps/market/services/signals/engine.py::compute_signals`, `apps/market/services/signals/bundles.py`, and the indicator primitives `macd_hist`/`adx`/`zscore`/`pct_b` in `apps/market/services/indicator.py`). P3 is independent of P2.

## Global Constraints

Repo global constraints (from the M16 interface contract — verbatim):

- Everything runs in Docker. One backend test:
  `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (WORKDIR /app/backend).
  One FE test: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`. Lint: `make lint`.
- Never set MOCK_EXTERNAL on the dev stack.
- Migrations gated by `make check-migrations`; beat tasks inventoried in `apps/core/scheduled_tasks.py`
  in the SAME commit (drift gate); worker/beat need `docker compose restart worker beat` after task changes.
- OpenAPI: `make schema` regenerates backend/schema.yml (commit it); `pnpm gen:api` runs on the HOST
  (broken inside the frontend container).
- DRF exposes FK ids as `*_id`. Section terminal state "done"; parent Snapshot "ready".
- Never log provider exceptions raw when the key rides in the URL — use `safe_err`.
- New FE components ship with co-located `*.stories.tsx` (storyless ratchet at ceiling) and a vitest test.
- Conventional commits (`feat(market):`, `feat(observer):`, `feat(frontend):`, `test:`, `docs:`); frequent.
- CI gate runs pytest `-p no:randomly`; coverage floors backend 86 branch, FE 80/74/77/82; ruff C901 ≤15.

P3-specific constraints (landmine-driven — every one of these is a silent failure if violated):

- **An exception escaping a metric recorder permanently disables the user's trigger** (`tasks.py::_disable_on_bad_condition`). Every new recorder catches ALL exceptions and degrades to an absent snapshot key (the evaluator treats a missing key as a silent no-match).
- **`evaluator.leaf_key()` falls through to the price branch** (`return f"price:{node['ticker']}"`). Every new metric MUST be routed by an explicit branch or an `_INDICATOR_KEY_PARAMS` entry, or it silently evaluates against the ticker's price.
- **`_INDICATOR_KEY_PARAMS` (evaluator.py) is a separate registry from `PARAMS_SPEC` (dsl.py)** — omit a param from `_INDICATOR_KEY_PARAMS` and two leaves with different params collide on one snapshot key AND one crossing-prior Redis key.
- **Raw-vs-resolved leaf_key landmine** — recorders write snapshot keys from RESOLVED params (`metrics._record_indicator` and `backtest.py:165-166` both key via `leaf_key({**leaf, "params": resolved_params(leaf)})`), but every evaluation path (`tasks.py` live, `views.py` dry-run, `backtest.py:182`) calls `leaf_key()` on the RAW node, where `str(params.get(pk))` renders a missing param as `"None"`. A parameterized indicator leaf WITHOUT explicit params is therefore written under `macd_hist:NVDA:1d:12:26:9` but read under `macd_hist:NVDA:1d:None:None:None` — it validates fine, backtests to zero matches, and silently never fires live. **Every plan-authored condition for the backtestable four that gets evaluated (presets, backtest tests, FE-emitted leaves, smoke checks) MUST carry explicit params.** (Task 4's params-less `test_macd_hist_leaf_computed_live` is the one deliberate exception: it asserts the RECORDED resolved key only and never evaluates — it characterizes default resolution at write time.)
- The live-only four join `NON_CROSSING_METRICS` (validation rejects crossing ops) — they get NO `_prior:` plumbing. The backtestable four inherit crossing support from the existing indicator pattern (`metrics.py:292-296` live, `backtest.py:179-180` replay).
- **No new beat tasks in this phase** — no `scheduled_tasks.py` or `config/celery.py` changes. The `triggers.evaluate_triggers` PeriodicTask is DB-seeded (observer migration 0016) and its name must never change.
- **No new float-typed DSL params** — every `PARAMS_SPEC` param is `int` (bool is deliberately rejected as an int); `bollinger_pct_b`'s `num_std` stays fixed at 2.0.
- The FE `Metric` union (`api/triggers.ts`), the `LeafRow.tsx` classification arrays, and `lib/triggers/describe.ts` are hand-synced with the backend — nothing is generated or drift-gated between them. Adding a metric means touching all three.
- Editing the `backtest` action docstring in `views.py` CHANGES `backend/schema.yml` (drf-spectacular embeds docstrings) — that commit must include `make schema` output AND host-side `pnpm gen:api` output (`frontend/src/api/schema.d.ts`), or the CI drift gate reds. Adding metrics themselves needs NO schema regen (`condition` is untyped JSON).
- `ruff C901 ≤15` — `indicator_value` and `describe._format_one` are near the ceiling; new branches go in the split-out helpers this plan specifies, not inline.
- `evaluate_triggers` gates each tick on `any_market_open(tickers_in_condition(...))` — the live-only positioning/sentiment metrics only evaluate while a referenced market is open. This is existing, accepted behavior; do not change the gate.
- After merge, run `docker compose restart worker beat` — the worker runs the evaluator loop with stale in-memory code otherwise (stale-worker landmine).

---

### Task 1: Register all eight metrics in the DSL validator

**Files:**
- Modify: `backend/apps/observer/triggers/dsl.py` (INDICATOR_METRICS literal at lines 29-37; new SIGNAL_METRICS block after the fundamentals block at lines 44-47; PARAMS_SPEC at lines 50-55; cross-field check in `_validate_params` after line 170)
- Test: create `backend/apps/observer/triggers/tests/test_dsl_signals.py`

**Interfaces:**
- Consumes (must already exist — P1 merged): `apps/market/services/signals/engine.py`, `apps/market/services/indicator.py` module-level fns `macd_hist`/`adx`/`zscore`/`pct_b`. Verified in step 1.
- Produces (later tasks rely on these exact names):
  - `dsl.SIGNAL_METRICS = {"iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment"}` (module-level set, importable — Task 5 imports it).
  - `dsl.INDICATOR_METRICS` now additionally contains `"macd_hist"`, `"adx"`, `"zscore"`, `"bollinger_pct_b"` (Tasks 3, 4, 6 rely on membership; `metrics.py` and `backtest.py` already import this set).
  - `dsl.PARAMS_SPEC` entries: `macd_hist: {fast:(int,12,2,100), slow:(int,26,3,200), signal:(int,9,2,50)}`, `adx: {period:(int,14,2,100)}`, `zscore: {period:(int,20,2,200)}`, `bollinger_pct_b: {period:(int,20,2,200)}`.
  - Validation semantics: backtestable four = ticker required, window required, params per spec, crossing ALLOWED; live-only four = ticker required, window FORBIDDEN, no params, crossing REJECTED.

**Steps:**

- [ ] Verify the P1 prerequisites exist (do NOT proceed if this fails — P1 is not merged):

```bash
docker compose exec web python -c "
from apps.market.services.signals.engine import compute_signals
from apps.market.services.signals.bundles import STRATEGY_TAGS
from apps.market.services.indicator import macd_hist, adx, zscore, pct_b
print('P1 OK')"
```

Expected output: `P1 OK`.

- [ ] Write the failing test file `backend/apps/observer/triggers/tests/test_dsl_signals.py` (full contents):

```python
"""DSL validation tests for the eight M16 signal metrics.

Backtestable indicator four (ticker + window required, params per spec, crossing allowed):
- macd_hist, adx, zscore, bollinger_pct_b
Live-only four (ticker required, window forbidden, no params, crossing rejected):
- iv_rank, put_call_vol, si_days_to_cover, news_sentiment
"""

import pytest
from django.core.exceptions import ValidationError

from apps.observer.triggers.dsl import validate_condition

INDICATOR_FOUR = ["macd_hist", "adx", "zscore", "bollinger_pct_b"]
LIVE_ONLY_FOUR = ["iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment"]


# ── backtestable indicator four ───────────────────────────────────────────────


@pytest.mark.parametrize("metric", INDICATOR_FOUR)
def test_indicator_metric_valid_leaf(metric):
    validate_condition({"metric": metric, "ticker": "NVDA", "op": ">", "value": 0, "window": "1d"})


@pytest.mark.parametrize("metric", INDICATOR_FOUR)
def test_indicator_metric_requires_ticker(metric):
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": metric, "op": ">", "value": 0, "window": "1d"})
    assert "ticker" in str(exc.value)


@pytest.mark.parametrize("metric", INDICATOR_FOUR)
def test_indicator_metric_requires_window(metric):
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": metric, "ticker": "NVDA", "op": ">", "value": 0})
    assert "window" in str(exc.value)


@pytest.mark.parametrize("metric", INDICATOR_FOUR)
def test_indicator_metric_allows_crossing(metric):
    validate_condition(
        {"metric": metric, "ticker": "NVDA", "op": "crosses_above", "value": 0, "window": "1d"}
    )


def test_macd_hist_params_validate():
    validate_condition(
        {
            "metric": "macd_hist",
            "ticker": "NVDA",
            "op": ">",
            "value": 0,
            "window": "1d",
            "params": {"fast": 12, "slow": 26, "signal": 9},
        }
    )


def test_macd_hist_rejects_fast_gte_slow():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "metric": "macd_hist",
                "ticker": "NVDA",
                "op": ">",
                "value": 0,
                "window": "1d",
                "params": {"fast": 26, "slow": 26},
            }
        )
    assert "fast" in str(exc.value)


def test_adx_rejects_unknown_param():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "metric": "adx",
                "ticker": "NVDA",
                "op": ">",
                "value": 25,
                "window": "1d",
                "params": {"fast": 5},
            }
        )
    assert "unknown keys" in str(exc.value)


@pytest.mark.parametrize("metric", ["zscore", "bollinger_pct_b"])
def test_period_bounds_enforced(metric):
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "metric": metric,
                "ticker": "NVDA",
                "op": ">",
                "value": 0,
                "window": "1d",
                "params": {"period": 1},
            }
        )
    assert "period" in str(exc.value)


# ── live-only four ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("metric", "op", "value"),
    [
        ("iv_rank", ">", 80),
        ("put_call_vol", ">", 1.5),
        ("si_days_to_cover", ">", 8),
        ("news_sentiment", "<", -0.3),
    ],
)
def test_live_only_valid_leaf(metric, op, value):
    validate_condition({"metric": metric, "ticker": "NVDA", "op": op, "value": value})


@pytest.mark.parametrize("metric", LIVE_ONLY_FOUR)
def test_live_only_requires_ticker(metric):
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": metric, "op": ">", "value": 1})
    assert "ticker" in str(exc.value)


@pytest.mark.parametrize("metric", LIVE_ONLY_FOUR)
def test_live_only_rejects_window(metric):
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": metric, "ticker": "NVDA", "op": ">", "value": 1, "window": "1d"}
        )
    assert "window" in str(exc.value)


@pytest.mark.parametrize("op", ["crosses_above", "crosses_below"])
@pytest.mark.parametrize("metric", LIVE_ONLY_FOUR)
def test_live_only_rejects_crossing(metric, op):
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": metric, "ticker": "NVDA", "op": op, "value": 1})
    assert "crossing" in str(exc.value)


@pytest.mark.parametrize("metric", LIVE_ONLY_FOUR)
def test_live_only_rejects_params(metric):
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": metric, "ticker": "NVDA", "op": ">", "value": 1, "params": {"period": 20}}
        )
    assert "unknown keys" in str(exc.value)
```

- [ ] Run it and confirm it fails on unknown metrics:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_dsl_signals.py -v
```

Expected: 45 tests collected; the vast majority FAIL. Positive tests fail with
`django.core.exceptions.ValidationError: [".metric: unknown metric 'macd_hist'"]` (etc.); negative tests fail on assertion (the raised message is `unknown metric ...`, which does not contain `ticker`/`window`/`crossing`).

- [ ] Implement in `backend/apps/observer/triggers/dsl.py`. Four edits.

Edit 1 — replace the `INDICATOR_METRICS` literal (currently lines 29-37) with:

```python
INDICATOR_METRICS = {
    "rsi",
    "sma_spread_pct",
    "atr_pct",
    "dist_from_sma_pct",
    "dist_from_52w_high",
    "dist_from_52w_low",
    "gap_pct",
    "macd_hist",
    "adx",
    "zscore",
    "bollinger_pct_b",
}
```

(The four new names ride the existing lines 39-42: `VALID_METRICS |= INDICATOR_METRICS`, `TICKER_REQUIRED |= INDICATOR_METRICS`, `WINDOW_REQUIRED |= INDICATOR_METRICS - DAILY_ONLY_METRICS`. They are NOT daily-only, so window is required — the window is the OHLC timeframe, exactly like `rsi`.)

Edit 2 — immediately after the `FUNDAMENTAL_METRICS` block (currently lines 44-47, ending `NON_CROSSING_METRICS |= FUNDAMENTAL_METRICS`), add:

```python
# M16 live-only signal metrics: resolved from the signals engine at tick time,
# absent from backtest per-bar snapshots. Slow-moving values — no crossing ops.
SIGNAL_METRICS = {"iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment"}
VALID_METRICS |= SIGNAL_METRICS
TICKER_REQUIRED |= SIGNAL_METRICS
NON_CROSSING_METRICS |= SIGNAL_METRICS
```

Edit 3 — extend `PARAMS_SPEC` (currently lines 50-55) to:

```python
# (type, default, min, max)
PARAMS_SPEC: dict[str, dict[str, tuple]] = {
    "rsi": {"period": (int, 14, 2, 100)},
    "atr_pct": {"period": (int, 14, 2, 100)},
    "dist_from_sma_pct": {"period": (int, 50, 2, 400)},
    "sma_spread_pct": {"fast": (int, 50, 2, 400), "slow": (int, 200, 3, 600)},
    "macd_hist": {
        "fast": (int, 12, 2, 100),
        "slow": (int, 26, 3, 200),
        "signal": (int, 9, 2, 50),
    },
    "adx": {"period": (int, 14, 2, 100)},
    "zscore": {"period": (int, 20, 2, 200)},
    "bollinger_pct_b": {"period": (int, 20, 2, 200)},
}
```

Edit 4 — in `_validate_params`, after the existing `sma_spread_pct` fast<slow check (currently lines 167-170), add:

```python
    if metric == "macd_hist":
        fast, slow = params.get("fast", 12), params.get("slow", 26)
        if fast >= slow:
            raise ValidationError(f"{path}.params: fast ({fast}) must be < slow ({slow})")
```

- [ ] Run again — all pass:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_dsl_signals.py -v
```

Expected: `45 passed`.

- [ ] Confirm no existing DSL test regressed:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_dsl_validation.py apps/observer/triggers/tests/test_dsl_indicators.py apps/observer/triggers/tests/test_dsl_fundamentals.py apps/observer/triggers/tests/test_dsl_properties.py -q
```

Expected: all passed.

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/dsl.py backend/apps/observer/triggers/tests/test_dsl_signals.py
git commit -m "feat(observer): register eight signal metrics in the trigger DSL

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Snapshot key shapes for the eight metrics (leaf_key)

**Files:**
- Modify: `backend/apps/observer/triggers/evaluator.py` (`_INDICATOR_KEY_PARAMS` at lines 43-51; new branch in `leaf_key()` after the fundamentals branch at lines 66-67)
- Test: create `backend/apps/observer/triggers/tests/test_metrics_signals.py` (this file grows in Tasks 4 and 5)

**Interfaces:**
- Consumes: Task 1's DSL registration (metric names valid). `evaluator.leaf_key(node: dict) -> str` — existing; the CRITICAL landmine is its fall-through default `return f"price:{node['ticker']}"` at line 76.
- Produces (exact key shapes later tasks and the FE describe path rely on):
  - `macd_hist:{ticker}:{window}:{fast}:{slow}:{signal}` e.g. `macd_hist:NVDA:1d:12:26:9`
  - `adx:{ticker}:{window}:{period}` e.g. `adx:NVDA:1d:14`
  - `zscore:{ticker}:{window}:{period}` e.g. `zscore:NVDA:1d:20`
  - `bollinger_pct_b:{ticker}:{window}:{period}` e.g. `bollinger_pct_b:NVDA:1d:20`
  - `iv_rank:{ticker}`, `put_call_vol:{ticker}`, `si_days_to_cover:{ticker}`, `news_sentiment:{ticker}`
  - `evaluator._SIGNAL_LEAF_METRICS` frozenset (module-level; internal to evaluator).

**Steps:**

- [ ] Create `backend/apps/observer/triggers/tests/test_metrics_signals.py` (full contents — later tasks append sections):

```python
"""Metrics-layer tests for the eight M16 signal metrics.

Sections (appended task-by-task):
- leaf_key shapes
- _bars_needed lookbacks + live recording of the backtestable four
- live-only recorders via the signals engine
"""

import pytest

from apps.observer.triggers.evaluator import leaf_key

# ── leaf_key shapes ───────────────────────────────────────────────────────────


def test_leaf_key_macd_hist():
    node = {
        "metric": "macd_hist",
        "ticker": "NVDA",
        "op": ">",
        "value": 0,
        "window": "1d",
        "params": {"fast": 12, "slow": 26, "signal": 9},
    }
    assert leaf_key(node) == "macd_hist:NVDA:1d:12:26:9"


def test_leaf_key_adx():
    node = {
        "metric": "adx",
        "ticker": "NVDA",
        "op": ">",
        "value": 25,
        "window": "1d",
        "params": {"period": 14},
    }
    assert leaf_key(node) == "adx:NVDA:1d:14"


def test_leaf_key_zscore():
    node = {
        "metric": "zscore",
        "ticker": "NVDA",
        "op": "<",
        "value": -2,
        "window": "1d",
        "params": {"period": 20},
    }
    assert leaf_key(node) == "zscore:NVDA:1d:20"


def test_leaf_key_bollinger_pct_b():
    node = {
        "metric": "bollinger_pct_b",
        "ticker": "NVDA",
        "op": "<",
        "value": 0,
        "window": "1d",
        "params": {"period": 20},
    }
    assert leaf_key(node) == "bollinger_pct_b:NVDA:1d:20"


def test_leaf_key_distinct_params_distinct_keys():
    a = {
        "metric": "zscore",
        "ticker": "NVDA",
        "op": "<",
        "value": -2,
        "window": "1d",
        "params": {"period": 20},
    }
    b = {**a, "params": {"period": 50}}
    assert leaf_key(a) != leaf_key(b)


@pytest.mark.parametrize(
    "metric", ["iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment"]
)
def test_leaf_key_live_only(metric):
    node = {"metric": metric, "ticker": "NVDA", "op": ">", "value": 1}
    assert leaf_key(node) == f"{metric}:NVDA"
```

- [ ] Run it and confirm the fall-through landmine fires:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_signals.py -v
```

Expected: 9 FAILED, every failure of the form `AssertionError: assert 'price:NVDA' == 'macd_hist:NVDA:1d:12:26:9'` — the new metrics currently fall through to the price branch.

- [ ] Implement in `backend/apps/observer/triggers/evaluator.py`. Two edits.

Edit 1 — extend `_INDICATOR_KEY_PARAMS` (currently lines 43-51) to (the params-sync trap: this tuple order defines the key layout; it MUST cover every `PARAMS_SPEC` param for the metric or distinct-params leaves collide on one key):

```python
_INDICATOR_KEY_PARAMS = {
    "rsi": ("period",),
    "atr_pct": ("period",),
    "dist_from_sma_pct": ("period",),
    "sma_spread_pct": ("fast", "slow"),
    "dist_from_52w_high": (),
    "dist_from_52w_low": (),
    "gap_pct": (),
    "macd_hist": ("fast", "slow", "signal"),
    "adx": ("period",),
    "zscore": ("period",),
    "bollinger_pct_b": ("period",),
}
```

Edit 2 — add a module constant after `_INDICATOR_KEY_PARAMS`, and a branch in `leaf_key()` between the fundamentals branch (currently lines 66-67) and the `_INDICATOR_KEY_PARAMS` branch (line 68):

```python
_SIGNAL_LEAF_METRICS = frozenset(
    {"iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment"}
)
```

```python
    if metric in _SIGNAL_LEAF_METRICS:
        return f"{metric}:{node['ticker']}"
```

(Keep the set literal local to the evaluator — this module is deliberately pure and imports nothing from `dsl.py`, mirroring the inline fundamentals set on line 66.)

- [ ] Run again:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_signals.py -v
```

Expected: `9 passed`.

- [ ] Confirm no evaluator regression:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_evaluator_compare.py apps/observer/triggers/tests/test_evaluator_crossings.py apps/observer/triggers/tests/test_evaluator_groups.py apps/observer/triggers/tests/test_metrics_indicators.py -q
```

Expected: all passed.

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/evaluator.py backend/apps/observer/triggers/tests/test_metrics_signals.py
git commit -m "feat(observer): leaf keys for the eight signal metrics

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Shared indicator dispatch for the backtestable four

**Files:**
- Modify: `backend/apps/observer/triggers/indicators.py` (import at line 10; new helper + one branch in `indicator_value()` at lines 58-98)
- Test: append to `backend/apps/observer/triggers/tests/test_indicators.py`

**Interfaces:**
- Consumes (P1 contract, exact signatures — all in `apps/market/services/indicator.py`):
  - `macd_hist(closes: list[float], *, fast: int = 12, slow: int = 26, signal: int = 9) -> float | None`
  - `adx(bars: list[dict], *, period: int = 14) -> float | None` (bars: `[{"high","low","close"},...]`)
  - `zscore(closes: list[float], *, period: int = 20) -> float | None`
  - `pct_b(closes: list[float], *, period: int = 20, num_std: float = 2.0) -> float | None`
- Produces: `indicator_value(metric, params, *, closes, bars, last, today_open=None, prev_close=None)` now resolves `"macd_hist"`, `"adx"`, `"zscore"`, `"bollinger_pct_b"` — tolerating `last=None` (they are closes/bars-only). This is the ONE dispatch shared by `metrics._record_indicator` (live) and `backtest.py:167` (replay); Tasks 4 and 6 depend on it and add NO math of their own.

**Steps:**

- [ ] Append to `backend/apps/observer/triggers/tests/test_indicators.py`:

```python
# ── M16 signal indicators via the shared dispatch ─────────────────────────────


def test_indicator_value_macd_hist_dispatch():
    closes = [100.0] * 40 + [100.0 + 2 * i for i in range(1, 21)]
    v = ind.indicator_value(
        "macd_hist", {"fast": 12, "slow": 26, "signal": 9}, closes=closes, bars=[], last=None
    )
    assert v is not None and v > 0  # fresh uptrend after a flat base -> positive histogram


def test_indicator_value_adx_dispatch():
    bars = [{"high": 101.0 + i, "low": 99.0 + i, "close": 100.0 + i} for i in range(60)]
    v = ind.indicator_value("adx", {"period": 14}, closes=[], bars=bars, last=None)
    assert v is not None and v > 25  # monotone trend -> strong ADX


def test_indicator_value_zscore_dispatch():
    closes = [float(100 + i) for i in range(30)]
    v = ind.indicator_value("zscore", {"period": 20}, closes=closes, bars=[], last=None)
    assert v is not None and v > 0  # last close above the 20-bar mean


def test_indicator_value_bollinger_pct_b_dispatch():
    closes = [float(100 + i) for i in range(30)]
    v = ind.indicator_value("bollinger_pct_b", {"period": 20}, closes=closes, bars=[], last=None)
    assert v is not None and v > 0.5  # rising series sits in the upper band


def test_indicator_value_zscore_insufficient_none():
    assert (
        ind.indicator_value("zscore", {"period": 20}, closes=[1.0, 2.0], bars=[], last=None)
        is None
    )
```

- [ ] Run and confirm failure:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_indicators.py -v
```

Expected: the 4 new dispatch tests FAIL with `AssertionError: assert None is not None ...` (the current `last is None and metric not in ("rsi", "sma_spread_pct")` guard short-circuits them); `test_indicator_value_zscore_insufficient_none` passes vacuously; all pre-existing tests pass.

- [ ] Implement in `backend/apps/observer/triggers/indicators.py`. Three edits.

Edit 1 — replace the import (currently line 10, `from apps.market.services.indicator import compute`) with:

```python
from apps.market.services.indicator import adx, compute, macd_hist, pct_b, zscore
```

Edit 2 — add, after the existing `atr_pct` function (line 55) and before `indicator_value`:

```python
SIGNAL_INDICATORS = frozenset({"macd_hist", "adx", "zscore", "bollinger_pct_b"})


def _signal_indicator_value(metric: str, params: dict, closes: list[float], bars: list[dict]):
    """The four M16 signal indicators. Closes/bars-only — none needs ``last``.

    Split out of indicator_value to stay under the ruff C901 complexity gate.
    """
    if metric == "macd_hist":
        return macd_hist(closes, fast=params["fast"], slow=params["slow"], signal=params["signal"])
    if metric == "adx":
        return adx(bars, period=params["period"])
    if metric == "zscore":
        return zscore(closes, period=params["period"])
    if metric == "bollinger_pct_b":
        return pct_b(closes, period=params["period"])
    return None
```

Edit 3 — inside `indicator_value`, add ONE branch as the first statement of the body, BEFORE the existing `if last is None and metric not in ("rsi", "sma_spread_pct"):` guard (line 78):

```python
    if metric in SIGNAL_INDICATORS:
        return _signal_indicator_value(metric, params, closes, bars)
```

- [ ] Run again:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_indicators.py -v
```

Expected: all passed (5 new + all pre-existing).

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/indicators.py backend/apps/observer/triggers/tests/test_indicators.py
git commit -m "feat(observer): dispatch macd_hist/adx/zscore/bollinger_pct_b via indicator_value

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Bar depth + live recording of the backtestable four (incl. crossing priors)

**Files:**
- Modify: `backend/apps/observer/triggers/metrics.py` (`_bars_needed` at lines 42-52 only — the recorder itself is the existing `_record_indicator`, reached by set membership)
- Test: append to `backend/apps/observer/triggers/tests/test_metrics_signals.py` (created in Task 2)

**Interfaces:**
- Consumes: Task 1 (`INDICATOR_METRICS` membership → `metrics._record_leaf` line 202 dispatches the four to `_record_indicator`, and `_ticker_union` line 329 fetches their quotes), Task 2 (key shapes), Task 3 (`indicator_value` dispatch). `dsl.resolved_params(leaf)` fills defaults.
- Produces: `_bars_needed(leaves) -> int` returns enough history for the new lookbacks: `macd_hist` → `slow + signal + 30` warm-up, `adx` → `2*period + 30`, both `+5` margin, hard cap `min(..., 500)` intact. With defaults: `macd_hist` → 70, `adx` → 63 (`zscore`/`bollinger_pct_b` are covered by the existing `period + 1` term). Crossing priors for the four come from the EXISTING indicator pattern (`_record_indicator` lines 292-296 writes `_prior:{resolved_key}` from Redis key `trigger:last:{resolved_key}`, TTL 3600) — no new code, proven by test.

**Steps:**

- [ ] Update the import block of `backend/apps/observer/triggers/tests/test_metrics_signals.py` (replace the current two import lines) with:

```python
from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.triggers import metrics
from apps.observer.triggers.evaluator import leaf_key
```

(`patch` is used by the fixture below; `fakeredis`/`metrics` by the new tests. `leaf_key` stays for the Task 2 section. In the Task 2 tests, `leaf_key` calls remain valid unchanged.)

- [ ] Append to the same file:

```python
# ── _bars_needed lookbacks ────────────────────────────────────────────────────


def test_bars_needed_macd_hist_defaults():
    leaf = {"metric": "macd_hist", "ticker": "NVDA", "op": ">", "value": 0, "window": "1d"}
    assert metrics._bars_needed([leaf]) == 70  # slow 26 + signal 9 + 30 warm-up + 5 margin


def test_bars_needed_adx_defaults():
    leaf = {"metric": "adx", "ticker": "NVDA", "op": ">", "value": 25, "window": "1d"}
    assert metrics._bars_needed([leaf]) == 63  # 2*14 + 30 + 5 margin


def test_bars_needed_macd_hist_custom_params_under_cap():
    leaf = {
        "metric": "macd_hist",
        "ticker": "NVDA",
        "op": ">",
        "value": 0,
        "window": "1d",
        "params": {"fast": 99, "slow": 200, "signal": 50},
    }
    assert metrics._bars_needed([leaf]) == 285  # 200 + 50 + 30 + 5; the 500 cap holds


def test_bars_needed_zscore_covered_by_period_term():
    leaf = {
        "metric": "zscore",
        "ticker": "NVDA",
        "op": "<",
        "value": -2,
        "window": "1d",
        "params": {"period": 60},
    }
    assert metrics._bars_needed([leaf]) == 66  # period 60 + 1, + 5 margin


# ── live recording of the backtestable four (shared indicator path) ──────────

RISING_BARS = [
    {"high": c + 1.0, "low": c - 1.0, "close": float(c), "open": float(c)} for c in range(1, 80)
]


@pytest.fixture
def fake_redis():
    client = fakeredis.FakeStrictRedis()
    with patch("apps.observer.triggers.metrics._redis", return_value=client):
        yield client


@pytest.mark.django_db
def test_adx_leaf_computed_live(fake_redis, monkeypatch):
    from apps.observer.models import EventTrigger
    from apps.profiles.models import TradingProfile

    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_ohlc", lambda *a, **k: RISING_BARS, raising=False
    )
    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_quotes", lambda *a, **k: {"NVDA": {"last": 80.0}}
    )
    p = TradingProfile.objects.create(name="P-adx", default_includes=["quotes"])
    t = EventTrigger.objects.create(
        name="adx",
        profile=p,
        condition={
            "metric": "adx",
            "ticker": "NVDA",
            "window": "1d",
            "op": ">",
            "value": 25,
            "params": {"period": 14},
        },
    )
    snap = metrics.build_snapshot([t])
    assert snap["adx:NVDA:1d:14"] is not None and snap["adx:NVDA:1d:14"] > 25


@pytest.mark.django_db
def test_macd_hist_leaf_computed_live(fake_redis, monkeypatch):
    from apps.observer.models import EventTrigger
    from apps.profiles.models import TradingProfile

    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_ohlc", lambda *a, **k: RISING_BARS, raising=False
    )
    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_quotes", lambda *a, **k: {"NVDA": {"last": 80.0}}
    )
    p = TradingProfile.objects.create(name="P-macd", default_includes=["quotes"])
    t = EventTrigger.objects.create(
        name="macd",
        profile=p,
        condition={"metric": "macd_hist", "ticker": "NVDA", "window": "1d", "op": ">", "value": 0},
    )
    snap = metrics.build_snapshot([t])
    assert snap["macd_hist:NVDA:1d:12:26:9"] is not None


@pytest.mark.django_db
def test_zscore_crossing_writes_prior_on_second_tick(fake_redis, monkeypatch):
    """The four inherit the indicator crossing pattern: _prior:{key} from trigger:last:{key}."""
    from apps.observer.models import EventTrigger
    from apps.profiles.models import TradingProfile

    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_ohlc", lambda *a, **k: RISING_BARS, raising=False
    )
    monkeypatch.setattr(
        "apps.observer.triggers.metrics.fetch_quotes", lambda *a, **k: {"NVDA": {"last": 80.0}}
    )
    p = TradingProfile.objects.create(name="P-z", default_includes=["quotes"])
    t = EventTrigger.objects.create(
        name="z",
        profile=p,
        condition={
            "metric": "zscore",
            "ticker": "NVDA",
            "window": "1d",
            "op": "crosses_below",
            "value": -2,
            "params": {"period": 20},
        },
    )
    first = metrics.build_snapshot([t])
    assert first["_prior:zscore:NVDA:1d:20"] is None  # cold start: no prior yet
    assert first["zscore:NVDA:1d:20"] is not None
    second = metrics.build_snapshot([t])
    assert second["_prior:zscore:NVDA:1d:20"] == pytest.approx(first["zscore:NVDA:1d:20"])
```

- [ ] Run and confirm ONLY the `_bars_needed` tests fail:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_signals.py -v
```

Expected: `test_bars_needed_macd_hist_defaults` FAILS with `assert 35 == 70`, `test_bars_needed_adx_defaults` FAILS with `assert 35 == 63`, `test_bars_needed_macd_hist_custom_params_under_cap` FAILS with `assert 206 == 285`; `test_bars_needed_zscore_covered_by_period_term` and every recording/crossing test PASS (they flow through the existing `_record_indicator` thanks to Tasks 1-3 — if any of them fails, a previous task regressed; fix it there, not here).

- [ ] Implement — replace `_bars_needed` in `backend/apps/observer/triggers/metrics.py` (currently lines 42-52) with:

```python
def _bars_needed(leaves: list[dict]) -> int:
    need = 30
    for lf in leaves:
        pr = resolved_params(lf)
        metric = lf["metric"]
        need = max(
            need,
            pr.get("period", 0) + 1,
            pr.get("slow", 0) + 1,
            252 if metric.startswith("dist_from_52w") else 0,
            # EMA-chain warm-up: MACD needs the slow EMA plus the signal EMA to
            # converge; ADX smooths twice over `period`.
            pr.get("slow", 0) + pr.get("signal", 0) + 30 if metric == "macd_hist" else 0,
            2 * pr.get("period", 0) + 30 if metric == "adx" else 0,
        )
    return min(need + 5, 500)
```

- [ ] Run again:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_signals.py -v
```

Expected: all passed (16 tests: 9 from Task 2 + 4 bars-needed + 3 recording/crossing).

- [ ] Guard against regressions in the sibling metric paths:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_indicators.py apps/observer/triggers/tests/test_metrics_edge_cases.py apps/observer/triggers/tests/test_metrics_quotes.py -q
```

Expected: all passed.

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/metrics.py backend/apps/observer/triggers/tests/test_metrics_signals.py
git commit -m "feat(observer): bar depth + live recording for the backtestable signal metrics

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Live-only recorders reading the signals engine

**Files:**
- Modify: `backend/apps/observer/triggers/metrics.py` (imports at lines 20-32; `_LeafContext` at lines 142-150; `build_snapshot` ctx construction at lines 123-129; new dispatch branch in `_record_leaf` after the fundamentals branch at lines 199-201; new `_record_signal` helper + `_SIGNAL_METRIC_SOURCE` map near `_FUND_METRIC_KEY` at lines 153-158)
- Test: append to `backend/apps/observer/triggers/tests/test_metrics_signals.py`

**Interfaces:**
- Consumes (P1 contract, exact signature — Task 5 is its only trigger-side consumer):
  - `apps.market.services.signals.engine.compute_signals(ticker: str, families: list[str] | None = None, *, benchmark: str = "$SPX") -> dict[str, dict[str, float | int | str | None]]` — `{family: {signal_name: value|None}}`, never raises, Redis-cached per (family, ticker) with TTLs `signals_vol=120s`, `signals_positioning=3600s` (so a 10s beat tick almost always hits the engine's own cache — no extra rate-limit pressure).
  - Signal names read: `vol_options.iv_rank_252`, `vol_options.put_call_vol`, `positioning.si_days_to_cover`, `positioning.news_sentiment_7d`.
  - `dsl.SIGNAL_METRICS` from Task 1; key shapes `"{metric}:{ticker}"` from Task 2.
- Produces:
  - `metrics._SIGNAL_METRIC_SOURCE: dict[str, tuple[str, str]]` — metric → (family, signal_name).
  - `metrics._record_signal(snapshot, key, metric, ticker, cache)` — resolves via `compute_signals`, one engine call per `(ticker, family)` per tick, catches ALL exceptions, writes only finite numeric values, leaves the key ABSENT otherwise.
  - `_LeafContext.signals_cache: dict[tuple[str, str], dict]` (per-tick).
  - Patch target for tests everywhere: `"apps.observer.triggers.metrics.compute_signals"` (module-level import — keep it; moving it breaks patch sites, the `ApiCredential` precedent).

**Steps:**

- [ ] Update the import block of `backend/apps/observer/triggers/tests/test_metrics_signals.py` to:

```python
from types import SimpleNamespace
from unittest.mock import patch

import fakeredis
import pytest

from apps.observer.triggers import metrics
from apps.observer.triggers.evaluator import evaluate, leaf_key
```

- [ ] Append to the same file:

```python
# ── live-only recorders via the signals engine ────────────────────────────────

ENGINE_PATCH = "apps.observer.triggers.metrics.compute_signals"

VOL_FAM = {"vol_options": {"iv_rank_252": 85.0, "iv_percentile_252": 90.0, "put_call_vol": 1.4}}
POS_FAM = {"positioning": {"si_days_to_cover": 9.5, "news_sentiment_7d": -0.42}}


def _trigger(condition):
    return SimpleNamespace(condition=condition)


def test_iv_rank_resolves_from_engine():
    cond = {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 80}
    with patch(ENGINE_PATCH, return_value=VOL_FAM) as mock_engine:
        snap = metrics.build_snapshot([_trigger(cond)])
    assert snap["iv_rank:NVDA"] == 85.0
    mock_engine.assert_called_once_with("NVDA", ["vol_options"])


def test_put_call_vol_resolves_from_engine():
    cond = {"metric": "put_call_vol", "ticker": "NVDA", "op": ">", "value": 1.2}
    with patch(ENGINE_PATCH, return_value=VOL_FAM):
        snap = metrics.build_snapshot([_trigger(cond)])
    assert snap["put_call_vol:NVDA"] == pytest.approx(1.4)


def test_si_days_to_cover_resolves_from_engine():
    cond = {"metric": "si_days_to_cover", "ticker": "GME", "op": ">", "value": 8}
    with patch(ENGINE_PATCH, return_value=POS_FAM) as mock_engine:
        snap = metrics.build_snapshot([_trigger(cond)])
    assert snap["si_days_to_cover:GME"] == pytest.approx(9.5)
    mock_engine.assert_called_once_with("GME", ["positioning"])


def test_news_sentiment_resolves_from_engine():
    cond = {"metric": "news_sentiment", "ticker": "NVDA", "op": "<", "value": -0.3}
    with patch(ENGINE_PATCH, return_value=POS_FAM):
        snap = metrics.build_snapshot([_trigger(cond)])
    assert snap["news_sentiment:NVDA"] == pytest.approx(-0.42)


def test_one_engine_call_per_ticker_family():
    cond = {
        "all": [
            {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 80},
            {"metric": "put_call_vol", "ticker": "NVDA", "op": ">", "value": 1.2},
        ]
    }
    with patch(ENGINE_PATCH, return_value=VOL_FAM) as mock_engine:
        metrics.build_snapshot([_trigger(cond)])
    mock_engine.assert_called_once_with("NVDA", ["vol_options"])


def test_distinct_families_two_engine_calls():
    cond = {
        "all": [
            {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 80},
            {"metric": "news_sentiment", "ticker": "NVDA", "op": "<", "value": -0.3},
        ]
    }

    def _by_family(_ticker, families):
        return VOL_FAM if families == ["vol_options"] else POS_FAM

    with patch(ENGINE_PATCH, side_effect=_by_family) as mock_engine:
        snap = metrics.build_snapshot([_trigger(cond)])
    assert mock_engine.call_count == 2
    assert snap["iv_rank:NVDA"] == 85.0
    assert snap["news_sentiment:NVDA"] == pytest.approx(-0.42)


def test_engine_none_value_leaf_absent():
    fam = {"vol_options": {"iv_rank_252": None, "put_call_vol": 1.4}}
    cond = {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 80}
    with patch(ENGINE_PATCH, return_value=fam):
        snap = metrics.build_snapshot([_trigger(cond)])
    assert "iv_rank:NVDA" not in snap


def test_engine_exception_leaf_absent_no_crash():
    """compute_signals never raises by contract, but the recorder must survive it anyway:
    an escaping exception would permanently disable the user's trigger."""
    cond = {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 80}
    with patch(ENGINE_PATCH, side_effect=RuntimeError("boom")):
        snap = metrics.build_snapshot([_trigger(cond)])
    assert "iv_rank:NVDA" not in snap


def test_engine_non_numeric_value_leaf_absent():
    fam = {"positioning": {"si_days_to_cover": "n/a", "news_sentiment_7d": True}}
    cond = {
        "any": [
            {"metric": "si_days_to_cover", "ticker": "NVDA", "op": ">", "value": 8},
            {"metric": "news_sentiment", "ticker": "NVDA", "op": ">", "value": 0},
        ]
    }
    with patch(ENGINE_PATCH, return_value=fam):
        snap = metrics.build_snapshot([_trigger(cond)])
    assert "si_days_to_cover:NVDA" not in snap
    assert "news_sentiment:NVDA" not in snap  # bool is not a metric value


def test_evaluate_iv_rank_end_to_end():
    cond = {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 80}
    with patch(ENGINE_PATCH, return_value=VOL_FAM):
        snap = metrics.build_snapshot([_trigger(cond)])
    matched, values = evaluate(cond, snap)
    assert matched is True
    assert values["iv_rank:NVDA"] == 85.0
```

- [ ] Run and confirm failure:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_signals.py -v
```

Expected: the 10 new tests FAIL with `AttributeError: <module 'apps.observer.triggers.metrics' ...> does not have the attribute 'compute_signals'`; the 16 pre-existing tests pass.

- [ ] Implement in `backend/apps/observer/triggers/metrics.py`. Five edits.

Edit 1 — add to the import block (after `from apps.market.services.quotes import fetch_quotes`, line 23):

```python
from apps.market.services.signals.engine import compute_signals
```

Edit 2 — extend the `dsl` import (lines 26-31) to include `SIGNAL_METRICS`:

```python
from apps.observer.triggers.dsl import (
    DAILY_ONLY_METRICS,
    FUNDAMENTAL_METRICS,
    INDICATOR_METRICS,
    SIGNAL_METRICS,
    resolved_params,
)
```

Edit 3 — extend `_LeafContext` (lines 142-150) with one field, and the ctx construction in `build_snapshot` (lines 123-129):

```python
@dataclass
class _LeafContext:
    """Per-tick inputs shared across the leaf recorders (assembled once in build_snapshot)."""

    quotes: dict[str, dict]
    positions_total_pl: float | None
    positions_total_mkt: float | None
    earnings_days: dict[str, int]
    fundamentals_cache: dict[str, dict]
    signals_cache: dict[tuple[str, str], dict]
```

```python
    ctx = _LeafContext(
        quotes=quotes,
        positions_total_pl=positions_total_pl,
        positions_total_mkt=positions_total_mkt,
        earnings_days=earnings_days,
        fundamentals_cache={},
        signals_cache={},
    )
```

Edit 4 — add the source map and recorder after `_record_fundamental` (which ends at line 257):

```python
_SIGNAL_METRIC_SOURCE = {
    "iv_rank": ("vol_options", "iv_rank_252"),
    "put_call_vol": ("vol_options", "put_call_vol"),
    "si_days_to_cover": ("positioning", "si_days_to_cover"),
    "news_sentiment": ("positioning", "news_sentiment_7d"),
}


def _record_signal(
    snapshot: dict[str, float | None],
    key: str,
    metric: str,
    ticker: str,
    cache: dict[tuple[str, str], dict],
) -> None:
    """Resolve a signals-engine metric, one compute_signals call per (ticker, family) per tick.

    Everything is caught: an exception escaping a recorder permanently disables
    the user's trigger (tasks._disable_on_bad_condition). Failure degrades to an
    absent key — the evaluator treats a missing key as a silent no-match.
    """
    family, signal_name = _SIGNAL_METRIC_SOURCE[metric]
    cache_key = (ticker.upper(), family)
    fam = cache.get(cache_key)
    if fam is None:
        try:
            fam = compute_signals(ticker.upper(), [family]).get(family) or {}
        except Exception as exc:
            log.warning("trigger.metrics.signals_failed %s/%s: %s", ticker, family, exc)
            fam = {}
        cache[cache_key] = fam
    raw = fam.get(signal_name)
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        snapshot[key] = float(raw)
    # absent when the engine returns None / a non-numeric — never invented
```

Edit 5 — add a dispatch branch in `_record_leaf`, between the `FUNDAMENTAL_METRICS` branch (lines 199-201) and the `INDICATOR_METRICS` branch (line 202):

```python
    elif metric in SIGNAL_METRICS:
        assert ticker is not None
        _record_signal(snapshot, key, metric, ticker, ctx.signals_cache)
```

(Do NOT add the live-only four to `_ticker_union` — they need no quotes. Verified implicitly: the new tests never patch `fetch_quotes`, so an unwanted quote fetch would log a warning and, in `test_iv_rank_resolves_from_engine`, real network would be attempted only if `_ticker_union` wrongly included the metric.)

- [ ] Run again:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_metrics_signals.py -v
```

Expected: `26 passed`.

- [ ] Sanity: the full metrics + evaluator surface:

```bash
docker compose exec web pytest apps/observer/triggers/tests/ -q -k "metrics or evaluator or dsl"
```

Expected: all passed.

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/metrics.py backend/apps/observer/triggers/tests/test_metrics_signals.py
git commit -m "feat(observer): live-only signal metrics read the signals engine

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Backtest replay proof + stale docstring fix (+ schema regen)

**Files:**
- Modify: `backend/apps/observer/triggers/views.py` (backtest action docstring, lines 94-100)
- Modify (generated, committed): `backend/schema.yml`, `frontend/src/api/schema.d.ts`
- Test: append to `backend/apps/observer/triggers/tests/test_backtest_indicators.py`

**Interfaces:**
- Consumes: Tasks 1-3. The backtest loop (`backtest.py:162-175`) already replays EVERY metric in `dsl.INDICATOR_METRICS` through the shared `indicator_value`, and populates `_prior:` keys generically from the previous bar (`backtest.py:179-180`) — the four backtestable metrics need ZERO `backtest.py` changes; these tests are characterization proof. Live-only metrics are absent from per-bar snapshots by construction (no branch writes them) — the established live-only mechanism, also proven here.
- Produces: nothing new at runtime. The `views.py` docstring edit flows into `backend/schema.yml` (drf-spectacular embeds docstrings — see the current stale text at `schema.yml` and `frontend/src/api/schema.d.ts:1753`), so this task MUST regenerate and commit both.

**Steps:**

- [ ] Append to `backend/apps/observer/triggers/tests/test_backtest_indicators.py` (file already imports `UTC, datetime, timedelta`, `pytest`, `OHLCBar`, `backtest`):

```python
# ── M16 signal indicators replay through the shared dispatch ─────────────────


@pytest.mark.django_db
def test_backtest_adx_trending():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(60):
        OHLCBar.objects.create(
            ticker="NVDA",
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100 + i,
            volume=1000,
        )
    cond = {
        "metric": "adx",
        "ticker": "NVDA",
        "window": "1d",
        "op": ">",
        "value": 25,
        "params": {"period": 14},
    }
    matches = backtest(cond, start=base, end=base + timedelta(days=90), timeframe="1d")
    assert len(matches) > 0  # monotone trend -> ADX far above 25 on later bars


@pytest.mark.django_db
def test_backtest_macd_hist_turns_positive():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    closes = [100.0] * 40 + [100.0 + 2 * i for i in range(1, 31)]
    for i, c in enumerate(closes):
        OHLCBar.objects.create(
            ticker="NVDA",
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1000,
        )
    # Explicit params are REQUIRED (raw-vs-resolved leaf_key landmine): backtest
    # evaluates the raw condition, so a params-less leaf reads the None-filled
    # key and never matches the resolved key the per-bar snapshot writes.
    cond = {
        "metric": "macd_hist",
        "ticker": "NVDA",
        "window": "1d",
        "op": ">",
        "value": 0,
        "params": {"fast": 12, "slow": 26, "signal": 9},
    }
    matches = backtest(cond, start=base, end=base + timedelta(days=120), timeframe="1d")
    assert len(matches) > 0  # histogram goes positive once the uptrend starts


@pytest.mark.django_db
def test_backtest_zscore_crossing_below_fires_once():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    # Gently alternating series (non-zero variance), one -20 spike, then recovery:
    # zscore crosses below -2 exactly on the spike bar.
    closes = [100.0 + (i % 2) for i in range(30)] + [80.0, 100.0, 101.0]
    for i, c in enumerate(closes):
        OHLCBar.objects.create(
            ticker="NVDA",
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1000,
        )
    cond = {
        "metric": "zscore",
        "ticker": "NVDA",
        "window": "1d",
        "op": "crosses_below",
        "value": -2,
        "params": {"period": 20},
    }
    matches = backtest(cond, start=base, end=base + timedelta(days=60), timeframe="1d")
    assert len(matches) == 1
    assert matches[0].ts == base + timedelta(days=30)  # the spike bar


@pytest.mark.django_db
def test_backtest_bollinger_pct_b_high_in_uptrend():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(40):
        c = 100.0 + i
        OHLCBar.objects.create(
            ticker="NVDA",
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1000,
        )
    cond = {
        "metric": "bollinger_pct_b",
        "ticker": "NVDA",
        "window": "1d",
        "op": ">",
        "value": 0.5,
        "params": {"period": 20},  # required — raw-vs-resolved leaf_key landmine
    }
    matches = backtest(cond, start=base, end=base + timedelta(days=60), timeframe="1d")
    assert len(matches) > 0  # a rising series rides the upper band


@pytest.mark.django_db
def test_backtest_live_only_metric_never_matches():
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(10):
        OHLCBar.objects.create(
            ticker="NVDA",
            timeframe="1d",
            ts=base + timedelta(days=i),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        )
    cond = {"metric": "iv_rank", "ticker": "NVDA", "op": ">", "value": 0}
    matches = backtest(cond, start=base, end=base + timedelta(days=30), timeframe="1d")
    assert matches == []  # live-only: absent from per-bar snapshots -> silent no-match
```

- [ ] Run — these are characterization tests and are expected to PASS on first run (the replay comes free from `INDICATOR_METRICS` membership plus the Task 3 dispatch; if any fails, first check that the test condition carries explicit params — a params-less parameterized leaf evaluates against the None-filled key and yields zero matches by the raw-vs-resolved leaf_key landmine, NOT a Task 1-3 regression; only with explicit params in place does a failure point at a previous task — fix it there):

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_backtest_indicators.py apps/observer/triggers/tests/test_backtest.py -v
```

Expected: all passed (2 pre-existing + 5 new in test_backtest_indicators, plus test_backtest.py untouched).

- [ ] Fix the stale docstring in `backend/apps/observer/triggers/views.py` — replace the backtest action docstring (lines 94-100):

Old:

```python
        """Replay a DSL condition over stored OHLC bars for [start, end].

        Body: {condition, start (ISO date), end (ISO date), timeframe?}
        Returns {match_count, matches:[{ts, values}]}. Only price/pct_change
        leaves are evaluated; other metrics are silently absent from the
        per-bar snapshot.
        """
```

New:

```python
        """Replay a DSL condition over stored OHLC bars for [start, end].

        Body: {condition, start (ISO date), end (ISO date), timeframe?}
        Returns {match_count, matches:[{ts, values, fwd_1d_pct, fwd_5d_pct}], summary}.
        Price, pct_change, vix, and all indicator leaves (rsi, sma_spread_pct,
        atr_pct, dist_from_sma_pct, dist_from_52w_*, gap_pct, macd_hist, adx,
        zscore, bollinger_pct_b) are replayed; live-only metrics are silently
        absent from the per-bar snapshot (they never match — not an error).
        """
```

- [ ] Regenerate the OpenAPI schema (the docstring is embedded in the operation description — skipping this reds the drift gate):

```bash
make schema
cd /home/dan/ledger/frontend && pnpm gen:api && cd /home/dan/ledger
```

(`pnpm gen:api` MUST run on the host — it fails silently inside the frontend container.) Expected: `git diff --stat` shows `backend/schema.yml` and `frontend/src/api/schema.d.ts` with the updated backtest description text.

- [ ] Run the endpoint tests to confirm nothing behavioral changed:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_endpoints_actions.py apps/observer/triggers/tests/test_endpoints_edge_cases.py -q
```

Expected: all passed.

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/tests/test_backtest_indicators.py backend/apps/observer/triggers/views.py backend/schema.yml frontend/src/api/schema.d.ts
git commit -m "test(observer): backtest replay coverage for signal indicators; fix stale backtest docstring

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Notification wording for the eight metrics (describe.py)

**Files:**
- Modify: `backend/apps/observer/triggers/services/describe.py` (new helper called first from `_format_one` at line 15)
- Test: append to `backend/apps/observer/triggers/tests/test_describe.py`

**Interfaces:**
- Consumes: leaf-key shapes from Task 2 (describe parses `matched_values` keys by string prefix — these strings reach the UI verbatim via `TriggerFiring.matched_values` and notification bodies).
- Produces: `_format_signal_one(key, value) -> str | None` (None = not a signal-metric key, caller falls through to the existing branches). Split out to keep `_format_one` under the ruff C901 ≤15 gate. Exact formats (pinned by tests): `NVDA MACD hist=0.457 / 1d`, `NVDA ADX(14)=27.3`, `NVDA z-score=-2.35 (20-bar)`, `NVDA %B=0.05 (20-bar)`, `NVDA IV rank=85`, `NVDA put/call vol=1.44`, `GME days-to-cover=9.5`, `NVDA news sentiment=-0.42`.

**Steps:**

- [ ] Append to `backend/apps/observer/triggers/tests/test_describe.py` (the file already has `from apps.observer.triggers.services.describe import describe` at the top):

```python
# ── M16 signal metrics ────────────────────────────────────────────────────────


def test_describe_macd_hist():
    assert describe({"macd_hist:NVDA:1d:12:26:9": 0.4567}) == "NVDA MACD hist=0.457 / 1d"


def test_describe_adx():
    assert describe({"adx:NVDA:1d:14": 27.31}) == "NVDA ADX(14)=27.3"


def test_describe_zscore():
    assert describe({"zscore:NVDA:1d:20": -2.351}) == "NVDA z-score=-2.35 (20-bar)"


def test_describe_bollinger_pct_b():
    assert describe({"bollinger_pct_b:NVDA:1d:20": 0.049}) == "NVDA %B=0.05 (20-bar)"


def test_describe_iv_rank():
    assert describe({"iv_rank:NVDA": 85.0}) == "NVDA IV rank=85"


def test_describe_put_call_vol():
    assert describe({"put_call_vol:NVDA": 1.44}) == "NVDA put/call vol=1.44"


def test_describe_si_days_to_cover():
    assert describe({"si_days_to_cover:GME": 9.53}) == "GME days-to-cover=9.5"


def test_describe_news_sentiment_negative():
    assert describe({"news_sentiment:NVDA": -0.42}) == "NVDA news sentiment=-0.42"


def test_describe_news_sentiment_positive_keeps_sign():
    assert describe({"news_sentiment:NVDA": 0.42}) == "NVDA news sentiment=+0.42"
```

- [ ] Run and confirm failure:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_describe.py -v
```

Expected: the 9 new tests FAIL on the generic fallback, e.g. `AssertionError: assert 'macd_hist:NVDA:1d:12:26:9=0.4567' == 'NVDA MACD hist=0.457 / 1d'`; pre-existing tests pass.

- [ ] Implement in `backend/apps/observer/triggers/services/describe.py`. Two edits.

Edit 1 — make `_format_one` (line 15) try the signal helper first — insert as the first two lines of its body:

```python
def _format_one(key: str, value: float) -> str:
    signal = _format_signal_one(key, value)
    if signal is not None:
        return signal
    if key.startswith("price:"):
```

(rest of the function unchanged.)

Edit 2 — add the helper at the end of the module:

```python
def _format_signal_one(key: str, value: float) -> str | None:
    """Wording for the M16 signal metrics; None when the key is not one of them.

    Split from _format_one to stay under the ruff C901 complexity gate.
    """
    if key.startswith("macd_hist:"):
        parts = key.split(":")
        return f"{parts[1]} MACD hist={value:.3f} / {parts[2]}"
    if key.startswith("adx:"):
        parts = key.split(":")
        return f"{parts[1]} ADX({parts[3]})={value:.1f}"
    if key.startswith("zscore:"):
        parts = key.split(":")
        return f"{parts[1]} z-score={value:.2f} ({parts[3]}-bar)"
    if key.startswith("bollinger_pct_b:"):
        parts = key.split(":")
        return f"{parts[1]} %B={value:.2f} ({parts[3]}-bar)"
    if key.startswith("iv_rank:"):
        _, ticker = key.split(":", 1)
        return f"{ticker} IV rank={value:.0f}"
    if key.startswith("put_call_vol:"):
        _, ticker = key.split(":", 1)
        return f"{ticker} put/call vol={value:.2f}"
    if key.startswith("si_days_to_cover:"):
        _, ticker = key.split(":", 1)
        return f"{ticker} days-to-cover={value:.1f}"
    if key.startswith("news_sentiment:"):
        _, ticker = key.split(":", 1)
        return f"{ticker} news sentiment={value:+.2f}"
    return None
```

- [ ] Run again:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_describe.py -v
```

Expected: all passed.

- [ ] Commit:

```bash
git add backend/apps/observer/triggers/services/describe.py backend/apps/observer/triggers/tests/test_describe.py
git commit -m "feat(observer): notification wording for signal metrics

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Per-tag trigger presets in bundles.py

**Files:**
- Modify: `backend/apps/market/services/signals/bundles.py` (created by P1)
- Test: create `backend/apps/observer/triggers/tests/test_trigger_presets.py`

**Interfaces:**
- Consumes: P1's `bundles.STRATEGY_TAGS = frozenset({"momentum", "mean_reversion", "vol_options", "positioning"})`; Task 1's DSL registration (every preset condition must validate).
- Produces (contract shape, exact): `bundles.TRIGGER_PRESETS: dict[str, list[dict]]` — tag → `[{"label": str, "condition": <DSL dict>}]`. Task 11's FE preset buttons hand-mirror a subset of these. `bundles.py` must NOT import anything from `apps.observer` (dependency direction: observer → market, never the reverse) — validation lives in the observer-side test.

**Steps:**

- [ ] Create `backend/apps/observer/triggers/tests/test_trigger_presets.py`:

```python
"""Every bundles.TRIGGER_PRESETS condition must be a valid trigger DSL condition.

The presets live in apps.market (bundles.py must not import the observer DSL —
wrong dependency direction), so the validation contract is enforced here.
"""

import pytest

from apps.market.services.signals.bundles import STRATEGY_TAGS, TRIGGER_PRESETS
from apps.observer.triggers.dsl import PARAMS_SPEC, validate_condition
from apps.observer.triggers.evaluator import iter_leaves

ALL_PRESETS = [p for presets in TRIGGER_PRESETS.values() for p in presets]


def test_preset_tags_are_exactly_the_strategy_tags():
    assert set(TRIGGER_PRESETS) == set(STRATEGY_TAGS)


def test_every_tag_has_at_least_one_preset():
    assert all(len(presets) >= 1 for presets in TRIGGER_PRESETS.values())


@pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p["label"])
def test_preset_condition_validates(preset):
    assert isinstance(preset["label"], str) and preset["label"]
    validate_condition(preset["condition"])


@pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p["label"])
def test_preset_parameterized_leaves_carry_explicit_params(preset):
    """Raw-vs-resolved leaf_key landmine: a parameterized indicator leaf WITHOUT
    explicit params is recorded under the resolved key but evaluated under the
    None-filled key — the preset would validate, backtest to zero matches, and
    silently never fire live. Every spec'd param must be pinned explicitly."""
    for leaf in iter_leaves(preset["condition"]):
        spec = PARAMS_SPEC.get(leaf["metric"])
        if not spec:
            continue
        params = leaf.get("params") or {}
        missing = set(spec) - set(params)
        assert not missing, (
            f"{preset['label']}: {leaf['metric']} leaf missing explicit params {missing} "
            "— dead trigger (raw-vs-resolved leaf_key mismatch)"
        )
```

- [ ] Run and confirm failure:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_trigger_presets.py -v
```

Expected failure — one of: `ImportError: cannot import name 'TRIGGER_PRESETS'` (P1 did not declare it), or `AssertionError` in `test_preset_tags_are_exactly_the_strategy_tags` (P1 left an empty placeholder `TRIGGER_PRESETS: dict[str, list[dict]] = {}`).

- [ ] Implement in `backend/apps/market/services/signals/bundles.py`: if P1 left a `TRIGGER_PRESETS` placeholder assignment, REPLACE it; otherwise append. Full block:

```python
# Suggested trigger presets per strategy tag. Plain dicts only — this module
# must not import the observer DSL (observer depends on market, never the
# reverse); apps/observer/triggers/tests/test_trigger_presets.py asserts every
# condition validates AND that every parameterized indicator leaf pins its
# params explicitly (a params-less leaf is a dead trigger: recorded under the
# resolved key, evaluated under the None-filled key). The FE builder
# hand-mirrors a subset as preset buttons
# (frontend/src/components/triggers/RuleBuilder.tsx).
TRIGGER_PRESETS: dict[str, list[dict]] = {
    "momentum": [
        {
            "label": "MACD histogram crosses above 0",
            "condition": {
                "metric": "macd_hist",
                "ticker": "SPY",
                "op": "crosses_above",
                "value": 0,
                "window": "1d",
                "params": {"fast": 12, "slow": 26, "signal": 9},
            },
        },
        {
            "label": "ADX > 25 (trend strength)",
            "condition": {
                "metric": "adx",
                "ticker": "SPY",
                "op": ">",
                "value": 25,
                "window": "1d",
                "params": {"period": 14},
            },
        },
    ],
    "mean_reversion": [
        {
            "label": "z-score < -2 (stretched down)",
            "condition": {
                "metric": "zscore",
                "ticker": "SPY",
                "op": "<",
                "value": -2,
                "window": "1d",
                "params": {"period": 20},
            },
        },
        {
            "label": "Bollinger %B < 0 (below lower band)",
            "condition": {
                "metric": "bollinger_pct_b",
                "ticker": "SPY",
                "op": "<",
                "value": 0,
                "window": "1d",
                "params": {"period": 20},
            },
        },
    ],
    "vol_options": [
        {
            "label": "IV rank > 80",
            "condition": {"metric": "iv_rank", "ticker": "SPY", "op": ">", "value": 80},
        },
        {
            "label": "Put/call volume > 1.5",
            "condition": {"metric": "put_call_vol", "ticker": "SPY", "op": ">", "value": 1.5},
        },
    ],
    "positioning": [
        {
            "label": "Days-to-cover > 8 (squeeze fuel)",
            "condition": {"metric": "si_days_to_cover", "ticker": "GME", "op": ">", "value": 8},
        },
        {
            "label": "News sentiment < -0.3",
            "condition": {"metric": "news_sentiment", "ticker": "SPY", "op": "<", "value": -0.3},
        },
    ],
}
```

- [ ] Run again:

```bash
docker compose exec web pytest apps/observer/triggers/tests/test_trigger_presets.py -v
```

Expected: `18 passed` (2 shape tests + 8 per-preset validations + 8 per-preset explicit-params pins).

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/bundles.py backend/apps/observer/triggers/tests/test_trigger_presets.py
git commit -m "feat(market): per-tag trigger presets in signal bundles

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: FE metric enumeration — 8 new + 5 missing existing metrics

**Files:**
- Modify: `frontend/src/api/triggers.ts` (`Metric` union at lines 7-10, `IndicatorParams` at lines 14-18)
- Modify: `frontend/src/components/triggers/LeafRow.tsx` (METRICS lines 4-18; TICKER_METRICS 24-28; WINDOW_METRICS 31; INDICATOR_METRICS 34-37; PERIOD_METRICS 40; FAST_SLOW_METRICS 43; params sub-form JSX 159-205)
- Test: append to `frontend/src/__tests__/TriggerEditorParams.test.tsx`

**Interfaces:**
- Consumes: backend metric names and semantics from Tasks 1-2 (hand-synced — nothing is generated for `condition`): backtestable four = ticker + window + params (macd_hist: fast/slow/signal defaults 12/26/9; adx: period 14; zscore & bollinger_pct_b: period 20); live-only four + `days_to_earnings` + `pe_ratio`/`market_cap`/`revenue_growth`/`gross_margin` = ticker only (no window, no params).
- Produces (Tasks 10-11 rely on these):
  - `Metric` union extended with all 13 names: `"days_to_earnings" | "pe_ratio" | "market_cap" | "revenue_growth" | "gross_margin" | "macd_hist" | "adx" | "zscore" | "bollinger_pct_b" | "iv_rank" | "put_call_vol" | "si_days_to_cover" | "news_sentiment"`.
  - `IndicatorParams` gains `signal?: number`.
  - LeafRow renders: `period` input for adx/zscore/bollinger_pct_b (defaults 14/20/20 via a new `DEFAULT_PERIOD` map), `fast period`/`slow period`/`signal period` inputs for macd_hist.
  - `LeafRow.patch()` SEEDS explicit default params when the metric changes to a parameterized one (alongside the existing ticker/window seeding). This is a correctness fix, not cosmetics: `DEFAULT_PERIOD` only changes what the input DISPLAYS — without seeding, a user who picks zscore/adx/bollinger_pct_b/macd_hist and accepts the displayed defaults saves a params-less leaf, which per the raw-vs-resolved leaf_key landmine silently never fires live and never matches in backtest. (This pre-existed for rsi; seeding fixes it for every period metric too.)

**Steps:**

- [ ] Append to `frontend/src/__tests__/TriggerEditorParams.test.tsx` (inside the existing `describe("TriggerEditorParams", ...)` block, before its closing `});`):

```tsx
  it("period input shows for adx leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "adx", ticker: "SPY", op: ">", value: 25, window: "1d" }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByLabelText("period")).toBeInTheDocument();
  });

  it("fast, slow and signal inputs show for macd_hist leaf", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{
        metric: "macd_hist", ticker: "SPY", op: ">", value: 0, window: "1d",
        params: { fast: 12, slow: 26, signal: 9 },
      }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByLabelText("fast period")).toBeInTheDocument();
    expect(screen.getByLabelText("slow period")).toBeInTheDocument();
    expect(screen.getByLabelText("signal period")).toBeInTheDocument();
  });

  it("zscore leaf defaults the period input display to 20", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "zscore", ticker: "SPY", op: "<", value: -2, window: "1d" }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect((screen.getByLabelText("period") as HTMLInputElement).value).toBe("20");
  });

  it("switching the metric to zscore seeds explicit default params", () => {
    // Dead-trigger guard: a params-less parameterized leaf is recorded under the
    // resolved key but evaluated under the None-filled key, so it never fires.
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("metric"), { target: { value: "zscore" } });
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaf = ("all" in emitted ? emitted.all[0] : emitted) as Leaf;
    expect(leaf.metric).toBe("zscore");
    expect(leaf.params?.period).toBe(20);
  });

  it("switching the metric to macd_hist seeds fast/slow/signal params", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("metric"), { target: { value: "macd_hist" } });
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaf = ("all" in emitted ? emitted.all[0] : emitted) as Leaf;
    expect(leaf.metric).toBe("macd_hist");
    expect(leaf.params).toEqual({ fast: 12, slow: 26, signal: 9 });
  });

  it("iv_rank leaf shows ticker but no window or params", () => {
    const onChange = vi.fn();
    const initial: Condition = {
      all: [{ metric: "iv_rank", ticker: "NVDA", op: ">", value: 80 }],
    };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    expect(screen.getByLabelText("ticker")).toBeInTheDocument();
    expect(screen.queryByLabelText("window")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("period")).not.toBeInTheDocument();
  });

  it("all thirteen newly-listed metrics are selectable", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    const metricSelect = screen.getByLabelText("metric") as HTMLSelectElement;
    const options = Array.from(metricSelect.options).map((o) => o.value);
    for (const m of [
      "days_to_earnings", "pe_ratio", "market_cap", "revenue_growth", "gross_margin",
      "macd_hist", "adx", "zscore", "bollinger_pct_b",
      "iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment",
    ]) {
      expect(options).toContain(m);
    }
  });
```

- [ ] Run and confirm failure:

```bash
docker compose exec frontend pnpm exec vitest run src/__tests__/TriggerEditorParams.test.tsx
```

Expected: the 7 new tests FAIL (`Unable to find a label with the text of: period`, missing `<option>` values, `expected undefined to be 20`, etc.); the 7 pre-existing tests pass.

- [ ] Implement `frontend/src/api/triggers.ts` — replace the `Metric` union (lines 7-10) and `IndicatorParams` (lines 14-18):

```ts
export type Metric =
  | "price" | "pct_change" | "volume_z" | "vix" | "position_pl" | "position_pl_pct"
  | "days_to_earnings"
  | "rsi" | "sma_spread_pct" | "atr_pct" | "dist_from_sma_pct"
  | "dist_from_52w_high" | "dist_from_52w_low" | "gap_pct"
  | "macd_hist" | "adx" | "zscore" | "bollinger_pct_b"
  | "pe_ratio" | "market_cap" | "revenue_growth" | "gross_margin"
  | "iv_rank" | "put_call_vol" | "si_days_to_cover" | "news_sentiment";
```

```ts
export type IndicatorParams = {
  period?: number;
  fast?: number;
  slow?: number;
  signal?: number;
};
```

- [ ] Implement `frontend/src/components/triggers/LeafRow.tsx`. Four edits.

Edit 1 — replace the classification constants (lines 4-43) with:

```tsx
const METRICS: { value: Metric; label: string }[] = [
  { value: "price", label: "price" },
  { value: "pct_change", label: "pct_change" },
  { value: "volume_z", label: "volume_z" },
  { value: "vix", label: "vix" },
  { value: "position_pl", label: "position_pl" },
  { value: "position_pl_pct", label: "position_pl_pct" },
  { value: "days_to_earnings", label: "days_to_earnings" },
  { value: "rsi", label: "rsi" },
  { value: "sma_spread_pct", label: "sma_spread_pct" },
  { value: "atr_pct", label: "atr_pct" },
  { value: "dist_from_sma_pct", label: "dist_from_sma_pct" },
  { value: "dist_from_52w_high", label: "dist_from_52w_high" },
  { value: "dist_from_52w_low", label: "dist_from_52w_low" },
  { value: "gap_pct", label: "gap_pct" },
  { value: "macd_hist", label: "macd_hist" },
  { value: "adx", label: "adx" },
  { value: "zscore", label: "zscore" },
  { value: "bollinger_pct_b", label: "bollinger_pct_b" },
  { value: "pe_ratio", label: "pe_ratio" },
  { value: "market_cap", label: "market_cap" },
  { value: "revenue_growth", label: "revenue_growth" },
  { value: "gross_margin", label: "gross_margin" },
  { value: "iv_rank", label: "iv_rank" },
  { value: "put_call_vol", label: "put_call_vol" },
  { value: "si_days_to_cover", label: "si_days_to_cover" },
  { value: "news_sentiment", label: "news_sentiment" },
];

const OPS: Op[] = [">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"];
const WINDOWS: Window[] = ["1m", "5m", "15m", "1h", "1d"];

// Metrics that require a ticker input
const TICKER_METRICS: Metric[] = [
  "price", "pct_change", "volume_z", "days_to_earnings",
  "rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct",
  "dist_from_52w_high", "dist_from_52w_low", "gap_pct",
  "macd_hist", "adx", "zscore", "bollinger_pct_b",
  "pe_ratio", "market_cap", "revenue_growth", "gross_margin",
  "iv_rank", "put_call_vol", "si_days_to_cover", "news_sentiment",
];

// Metrics that require a window selector (excludes daily-only)
const WINDOW_METRICS: Metric[] = [
  "pct_change", "volume_z", "rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct",
  "macd_hist", "adx", "zscore", "bollinger_pct_b",
];

// Indicator metrics that expose a params sub-form
const INDICATOR_METRICS: Metric[] = [
  "rsi", "sma_spread_pct", "atr_pct", "dist_from_sma_pct",
  "dist_from_52w_high", "dist_from_52w_low", "gap_pct",
  "macd_hist", "adx", "zscore", "bollinger_pct_b",
];

// Metrics that use a single "period" param
const PERIOD_METRICS: Metric[] = ["rsi", "atr_pct", "dist_from_sma_pct", "adx", "zscore", "bollinger_pct_b"];

// Displayed default when the leaf has no explicit period param (backend defaults).
const DEFAULT_PERIOD: Partial<Record<Metric, number>> = {
  rsi: 14, atr_pct: 14, dist_from_sma_pct: 50, adx: 14, zscore: 20, bollinger_pct_b: 20,
};

// Metrics that use fast/slow params
const FAST_SLOW_METRICS: Metric[] = ["sma_spread_pct"];

// MACD uses fast/slow/signal params
const MACD_METRICS: Metric[] = ["macd_hist"];
```

Edit 2 — replace the `patch` function (currently lines 63-74) with (the new `else if` block seeds explicit default params on metric change — without it, accepting the DISPLAYED defaults saves a params-less leaf that is recorded under the resolved key but evaluated under the None-filled key: a trigger that silently never fires live and never matches in backtest):

```tsx
  function patch(p: Partial<Leaf>) {
    let next: Leaf = { ...leaf, ...p };
    // Normalize when metric changes: drop fields that no longer apply.
    if (p.metric && p.metric !== leaf.metric) {
      if (!needsTicker(p.metric)) delete (next as Partial<Leaf>).ticker;
      else if (!leaf.ticker) next = { ...next, ticker: "SPY" };
      if (!needsWindow(p.metric)) delete (next as Partial<Leaf>).window;
      else if (!leaf.window) next = { ...next, window: "5m" };
      if (!needsParams(p.metric)) delete (next as Partial<Leaf>).params;
      // Seed explicit default params: a params-less parameterized leaf is a
      // dead trigger (raw-vs-resolved leaf_key mismatch on the backend).
      else if (!next.params) {
        if (PERIOD_METRICS.includes(p.metric)) {
          next = { ...next, params: { period: DEFAULT_PERIOD[p.metric] ?? 14 } };
        } else if (p.metric === "macd_hist") {
          next = { ...next, params: { fast: 12, slow: 26, signal: 9 } };
        } else if (p.metric === "sma_spread_pct") {
          next = { ...next, params: { fast: 50, slow: 200 } };
        }
        // dist_from_52w_*/gap_pct take no params — leave params absent.
      }
    }
    onChange(next);
  }
```

Edit 3 — in the component body, replace the two `show*` lines (currently lines 83-84) with:

```tsx
  const showPeriod = PERIOD_METRICS.includes(leaf.metric);
  const showFastSlow = FAST_SLOW_METRICS.includes(leaf.metric);
  const showMacd = MACD_METRICS.includes(leaf.metric);
```

and inside the period input JSX (line 170), change the value expression to use the per-metric default:

```tsx
                value={params.period ?? DEFAULT_PERIOD[leaf.metric] ?? 14}
```

Edit 4 — after the `{showFastSlow && (...)}` fragment (ends line 203), add the MACD sub-form as a sibling:

```tsx
          {showMacd && (
            <>
              <label className="flex items-center gap-1">
                <span>fast</span>
                <input
                  aria-label="fast period"
                  type="number"
                  min={2}
                  max={100}
                  value={params.fast ?? 12}
                  onChange={(e) => patchParam("fast", e.target.value)}
                  className="bg-neutral-800 px-2 py-0.5 rounded w-16 text-ink-100"
                />
              </label>
              <label className="flex items-center gap-1">
                <span>slow</span>
                <input
                  aria-label="slow period"
                  type="number"
                  min={3}
                  max={200}
                  value={params.slow ?? 26}
                  onChange={(e) => patchParam("slow", e.target.value)}
                  className="bg-neutral-800 px-2 py-0.5 rounded w-16 text-ink-100"
                />
              </label>
              <label className="flex items-center gap-1">
                <span>signal</span>
                <input
                  aria-label="signal period"
                  type="number"
                  min={2}
                  max={50}
                  value={params.signal ?? 9}
                  onChange={(e) => patchParam("signal", e.target.value)}
                  className="bg-neutral-800 px-2 py-0.5 rounded w-16 text-ink-100"
                />
              </label>
            </>
          )}
```

- [ ] Run again:

```bash
docker compose exec frontend pnpm exec vitest run src/__tests__/TriggerEditorParams.test.tsx src/__tests__/RuleBuilder.test.tsx
```

Expected: all passed (14 in TriggerEditorParams + all RuleBuilder tests).

- [ ] Type-check (tsc is a real gate):

```bash
docker compose exec frontend pnpm exec tsc --noEmit
```

Expected: exit 0, no output.

- [ ] Commit:

```bash
git add frontend/src/api/triggers.ts frontend/src/components/triggers/LeafRow.tsx frontend/src/__tests__/TriggerEditorParams.test.tsx
git commit -m "feat(frontend): trigger builder metrics for signals + missing fundamentals

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: FE human-readable descriptions (describe.ts)

**Files:**
- Modify: `frontend/src/lib/triggers/describe.ts` (import at line 1; new phrase tables; branches in `describeLeaf` before the fallback at line 52)
- Test: append to `frontend/src/__tests__/describeTrigger.test.ts`

**Interfaces:**
- Consumes: the extended `Metric` union from Task 9 (`frontend/src/api/triggers.ts`); `OP_WORDS` map already in describe.ts.
- Produces: `describeLeaf` wording for all 13 new metrics (exact strings pinned below); unknown metrics still fall through to the generic sentence.

**Steps:**

- [ ] Append to `frontend/src/__tests__/describeTrigger.test.ts` (inside the `describe("describeLeaf", ...)` block, before its closing `});`):

```ts
  it("formats days_to_earnings", () => {
    expect(describeLeaf({ metric: "days_to_earnings", ticker: "NVDA", op: "<=", value: 3 }))
      .toBe("NVDA earnings is less than or equal to 3 days away");
  });

  it("formats pe_ratio", () => {
    expect(describeLeaf({ metric: "pe_ratio", ticker: "NVDA", op: "<", value: 30 }))
      .toBe("NVDA P/E is less than 30");
  });

  it("formats market_cap", () => {
    expect(describeLeaf({ metric: "market_cap", ticker: "NVDA", op: ">=", value: 1e12 }))
      .toBe("NVDA market cap is greater than or equal to 1000000000000");
  });

  it("formats revenue_growth", () => {
    expect(describeLeaf({ metric: "revenue_growth", ticker: "NVDA", op: ">", value: 0.1 }))
      .toBe("NVDA revenue growth is greater than 0.1");
  });

  it("formats gross_margin", () => {
    expect(describeLeaf({ metric: "gross_margin", ticker: "NVDA", op: ">", value: 60 }))
      .toBe("NVDA gross margin is greater than 60");
  });

  it("formats macd_hist with window", () => {
    expect(describeLeaf({
      metric: "macd_hist", ticker: "SPY", op: "crosses_above", value: 0, window: "1d",
    })).toBe("SPY MACD histogram crosses above 0 over 1d");
  });

  it("formats adx with window", () => {
    expect(describeLeaf({ metric: "adx", ticker: "SPY", op: ">", value: 25, window: "1d" }))
      .toBe("SPY ADX is greater than 25 over 1d");
  });

  it("formats zscore with window", () => {
    expect(describeLeaf({ metric: "zscore", ticker: "SPY", op: "<", value: -2, window: "1d" }))
      .toBe("SPY z-score is less than -2 over 1d");
  });

  it("formats bollinger_pct_b with window", () => {
    expect(describeLeaf({
      metric: "bollinger_pct_b", ticker: "SPY", op: "<", value: 0, window: "1d",
    })).toBe("SPY Bollinger %B is less than 0 over 1d");
  });

  it("formats iv_rank", () => {
    expect(describeLeaf({ metric: "iv_rank", ticker: "NVDA", op: ">", value: 80 }))
      .toBe("NVDA IV rank is greater than 80");
  });

  it("formats put_call_vol", () => {
    expect(describeLeaf({ metric: "put_call_vol", ticker: "NVDA", op: ">", value: 1.5 }))
      .toBe("NVDA put/call volume is greater than 1.5");
  });

  it("formats si_days_to_cover", () => {
    expect(describeLeaf({ metric: "si_days_to_cover", ticker: "GME", op: ">", value: 8 }))
      .toBe("GME short interest days-to-cover is greater than 8");
  });

  it("formats news_sentiment", () => {
    expect(describeLeaf({ metric: "news_sentiment", ticker: "NVDA", op: "<", value: -0.3 }))
      .toBe("NVDA 7-day news sentiment is less than -0.3");
  });
```

- [ ] Run and confirm failure:

```bash
docker compose exec frontend pnpm exec vitest run src/__tests__/describeTrigger.test.ts
```

Expected: the 13 new tests FAIL on the generic fallback, e.g. `expected 'pe_ratio of NVDA is less than 30' to be 'NVDA P/E is less than 30'`; pre-existing tests pass.

- [ ] Implement `frontend/src/lib/triggers/describe.ts`. Three edits.

Edit 1 — extend the type import (line 1):

```ts
import type { Condition, Leaf, Metric, Op } from "@/api/triggers";
```

Edit 2 — add two phrase tables after `OP_WORDS` (line 11):

```ts
// "{ticker} {phrase} {op} {value}" — ticker-scoped metrics with no window.
const TICKER_PHRASES: Partial<Record<Metric, string>> = {
  pe_ratio: "P/E",
  market_cap: "market cap",
  revenue_growth: "revenue growth",
  gross_margin: "gross margin",
  iv_rank: "IV rank",
  put_call_vol: "put/call volume",
  si_days_to_cover: "short interest days-to-cover",
  news_sentiment: "7-day news sentiment",
};

// "{ticker} {phrase} {op} {value} over {window}" — windowed signal indicators.
const WINDOWED_PHRASES: Partial<Record<Metric, string>> = {
  macd_hist: "MACD histogram",
  adx: "ADX",
  zscore: "z-score",
  bollinger_pct_b: "Bollinger %B",
};
```

Edit 3 — in `describeLeaf`, insert before the `// price` fallback (line 51):

```ts
  if (metric === "days_to_earnings") {
    return `${ticker} earnings ${OP_WORDS[op]} ${value} days away`;
  }

  const windowedPhrase = WINDOWED_PHRASES[metric];
  if (windowedPhrase) {
    return `${ticker} ${windowedPhrase} ${OP_WORDS[op]} ${value} over ${window}`;
  }

  const tickerPhrase = TICKER_PHRASES[metric];
  if (tickerPhrase) {
    return `${ticker} ${tickerPhrase} ${OP_WORDS[op]} ${value}`;
  }
```

- [ ] Run again:

```bash
docker compose exec frontend pnpm exec vitest run src/__tests__/describeTrigger.test.ts
```

Expected: all passed.

- [ ] Commit:

```bash
git add frontend/src/lib/triggers/describe.ts frontend/src/__tests__/describeTrigger.test.ts
git commit -m "feat(frontend): describeLeaf wording for signal + fundamental metrics

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: FE preset buttons + stale backtest copy fix

**Files:**
- Modify: `frontend/src/components/triggers/RuleBuilder.tsx` (SMA_CROSS_PRESET at lines 29-36 → PRESETS array; button block at lines 61-70 → mapped buttons)
- Modify: `frontend/src/pages/trigger-editor/BacktestPanel.tsx` (stale copy at lines 20-23)
- Test: append to `frontend/src/__tests__/TriggerEditorParams.test.tsx`

**Interfaces:**
- Consumes: Task 9's `Metric` union + LeafRow behavior; Task 8's backend `TRIGGER_PRESETS` (hand-mirrored — the FE buttons are a curated subset, one per tag plus the existing SMA cross; there is no presets API endpoint).
- Produces: five preset buttons with aria-labels `"<name> preset"`: `SMA cross`, `MACD cross`, `z-score dip`, `IV rank`, `Days-to-cover`. The existing `SMA cross preset` aria-label and emitted leaf are byte-identical to before (pre-existing tests keep passing).

**Steps:**

- [ ] Append to `frontend/src/__tests__/TriggerEditorParams.test.tsx` (inside the `describe` block):

```tsx
  it("all five preset buttons render", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    for (const name of ["SMA cross", "MACD cross", "z-score dip", "IV rank", "Days-to-cover"]) {
      expect(screen.getByRole("button", { name: new RegExp(name, "i") })).toBeInTheDocument();
    }
  });

  it("clicking the z-score dip preset emits a zscore leaf with period param", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /z-score dip/i }));
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaves = ("all" in emitted ? emitted.all : []) as Leaf[];
    const newLeaf = leaves[leaves.length - 1];
    expect(newLeaf.metric).toBe("zscore");
    expect(newLeaf.op).toBe("<");
    expect(newLeaf.value).toBe(-2);
    expect(newLeaf.window).toBe("1d");
    expect(newLeaf.params?.period).toBe(20);
  });

  it("clicking the IV rank preset emits an iv_rank leaf without window", () => {
    const onChange = vi.fn();
    const initial: Condition = { all: [{ metric: "price", ticker: "SPY", op: ">", value: 0 }] };
    render(<RuleBuilder value={initial} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /IV rank/i }));
    const emitted = onChange.mock.calls.at(-1)![0] as Condition;
    const leaves = ("all" in emitted ? emitted.all : []) as Leaf[];
    const newLeaf = leaves[leaves.length - 1];
    expect(newLeaf.metric).toBe("iv_rank");
    expect(newLeaf.op).toBe(">");
    expect(newLeaf.value).toBe(80);
    expect(newLeaf.window).toBeUndefined();
  });
```

- [ ] Run and confirm failure:

```bash
docker compose exec frontend pnpm exec vitest run src/__tests__/TriggerEditorParams.test.tsx
```

Expected: the 3 new tests FAIL (`Unable to find an accessible element with the role "button" and name /MACD cross/i` etc.); the 14 others pass.

- [ ] Implement `frontend/src/components/triggers/RuleBuilder.tsx`. Two edits.

Edit 1 — replace the `SMA_CROSS_PRESET` constant (lines 29-36) with:

```tsx
// Hand-mirrored subset of the backend per-tag presets
// (backend/apps/market/services/signals/bundles.py TRIGGER_PRESETS).
const PRESETS: { name: string; leaf: Leaf }[] = [
  {
    name: "SMA cross",
    leaf: {
      metric: "sma_spread_pct", ticker: "SPY", op: "crosses_above", value: 0,
      window: "1d", params: { fast: 50, slow: 200 },
    },
  },
  {
    name: "MACD cross",
    leaf: {
      metric: "macd_hist", ticker: "SPY", op: "crosses_above", value: 0,
      window: "1d", params: { fast: 12, slow: 26, signal: 9 },
    },
  },
  {
    name: "z-score dip",
    leaf: {
      metric: "zscore", ticker: "SPY", op: "<", value: -2,
      window: "1d", params: { period: 20 },
    },
  },
  { name: "IV rank", leaf: { metric: "iv_rank", ticker: "SPY", op: ">", value: 80 } },
  { name: "Days-to-cover", leaf: { metric: "si_days_to_cover", ticker: "GME", op: ">", value: 8 } },
];
```

Edit 2 — replace the single preset button block (lines 61-70, `{!readOnly && (<button ... + SMA cross</button>)}`) with:

```tsx
        {!readOnly && (
          <span className="ml-auto flex gap-1 flex-wrap">
            {PRESETS.map((p) => (
              <button
                key={p.name}
                type="button"
                aria-label={`${p.name} preset`}
                onClick={() => emit([...leaves, { ...p.leaf }])}
                className="text-xs bg-neutral-800 hover:bg-neutral-700 px-2 py-1 rounded text-indigo-400 hover:text-indigo-300"
              >
                + {p.name}
              </button>
            ))}
          </span>
        )}
```

- [ ] Fix the stale copy in `frontend/src/pages/trigger-editor/BacktestPanel.tsx` — replace the description div (lines 20-23):

Old:

```tsx
      <div className="text-sm text-neutral-400">
        Replay the current condition against stored OHLC bars. Only <code>price</code> and
        <code>pct_change</code> leaves evaluate; live-only metrics are skipped.
      </div>
```

New:

```tsx
      <div className="text-sm text-neutral-400">
        Replay the current condition against stored OHLC bars. <code>price</code>,{" "}
        <code>pct_change</code>, <code>vix</code> and indicator leaves (RSI, SMA spread, ATR,
        MACD, ADX, z-score, %B, …) evaluate; live-only metrics are skipped.
      </div>
```

- [ ] Run the full trigger-related FE surface:

```bash
docker compose exec frontend pnpm exec vitest run src/__tests__/TriggerEditorParams.test.tsx src/__tests__/RuleBuilder.test.tsx src/__tests__/TriggerEditorPage.test.tsx src/__tests__/describeTrigger.test.ts
```

Expected: all passed (the pre-existing "SMA cross preset" tests still pass — same aria-label, same emitted leaf).

- [ ] Type-check:

```bash
docker compose exec frontend pnpm exec tsc --noEmit
```

Expected: exit 0.

- [ ] Commit:

```bash
git add frontend/src/components/triggers/RuleBuilder.tsx frontend/src/pages/trigger-editor/BacktestPanel.tsx frontend/src/__tests__/TriggerEditorParams.test.tsx
git commit -m "feat(frontend): trigger preset buttons; fix stale backtest copy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Full verification sweep

**Files:** none created/modified (fix-forward in the owning task's files if anything reds).

**Interfaces:** Consumes everything above. Produces a green gate.

**Steps:**

- [ ] Backend: the whole triggers surface plus the bundles consumer:

```bash
docker compose exec web pytest apps/observer/triggers/ -q
```

Expected: all passed (includes test_dsl_signals 45, test_metrics_signals 26, test_trigger_presets 18, plus the extended test_indicators/test_backtest_indicators/test_describe and every pre-existing file).

- [ ] Backend: adjacent suites that import the touched modules:

```bash
docker compose exec web pytest apps/observer/ apps/market/ -q
```

Expected: all passed.

- [ ] Frontend: full vitest run (coverage floors 80/74/77/82 must hold):

```bash
docker compose exec frontend pnpm exec vitest run
```

Expected: all passed; coverage above thresholds.

- [ ] Lint everything (ruff incl. C901/S, mypy zero-baseline, import-linter, deptry, semgrep rules; FE eslint, depcruise, type-coverage):

```bash
make lint
```

Expected: exit 0. If `C901` flags `indicator_value` or `_format_one`, the split-helper structure from Tasks 3/7 was not followed — restore it.

- [ ] Confirm the OpenAPI drift gate is clean (Task 6 committed both generated files):

```bash
make schema && git diff --stat backend/schema.yml frontend/src/api/schema.d.ts
```

Expected: empty diff.

- [ ] Restart the long-running services so the live evaluator picks up the new code (stale-worker landmine — `exec` checks are false positives):

```bash
docker compose restart worker beat
```

- [ ] Optional live smoke (dev stack, requires market data configured): create a trigger via the UI or POST `/api/triggers/evaluate/` with `{"condition": {"metric": "zscore", "ticker": "SPY", "op": "<", "value": -2, "window": "1d", "params": {"period": 20}}}` — expect `{matched, values: {"zscore:SPY:1d:20": ...}, missing: [...]}` with the correct key shape (the dry-run endpoint exercises the full recorder path with no extra code; params are explicit because the dry-run, like every evaluation path, keys off the RAW condition — the raw-vs-resolved leaf_key landmine).

---

## Deviations / notes

- **No `backtest.py` code change**: the phase scope lists "backtest.py per-bar replay + crossing prior keys" — both are satisfied structurally (the four join `INDICATOR_METRICS`, whose per-bar replay block at `backtest.py:162-175` and generic `_prior:` population at `:179-180` already exist) and are proven by the Task 6 characterization tests rather than re-implemented. The file wins over the map.
- **`zscore`/`bollinger_pct_b` take a `period` param (default 20)** — the parameterized generalization of the engine's fixed `zscore_20d`/`bollinger_pct_b` signal names, per the contract.
- **Live-only recorders route ALL four metrics through `compute_signals`** (not raw model reads): `iv_rank`→`vol_options.iv_rank_252`, `put_call_vol`→`vol_options.put_call_vol`, `si_days_to_cover`→`positioning.si_days_to_cover`, `news_sentiment`→`positioning.news_sentiment_7d`. The engine's own Redis cache (120s/3600s TTLs) absorbs the 10s tick rate; the per-tick `signals_cache` dict dedupes within a tick (the fundamentals-cache pattern — a lazy cache, so no eager `needs_x` prefetch is required in `build_snapshot`).
- **Market-hours gate**: live-only positioning/sentiment leaves only evaluate while a referenced market is open (existing `any_market_open` gate) — accepted, unchanged.
- **Raw-vs-resolved leaf_key: fixed at the authoring surfaces, not the evaluator.** Recorders key snapshots by RESOLVED params while every evaluation path keys by the RAW node, so a params-less parameterized leaf is a silent dead trigger (see Global Constraints). This plan closes every authoring surface it ships — backend presets pin explicit params (Task 8, gated by `test_preset_parameterized_leaves_carry_explicit_params`), `LeafRow.patch()` seeds explicit defaults on metric change (Task 9), and every plan-authored test/smoke condition carries params. The deeper backend fix (evaluation paths resolving params before keying, e.g. via `dsl.resolved_params` in tasks.py/views.py/backtest.py) is deliberately OUT of P3 scope — it touches every evaluation path plus regression tests and would also change behavior for pre-existing rsi/sma_spread_pct leaves saved without params; if wanted, it is a separate follow-up.
