# M16 P5 — Regime + Coverage Signal Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feed the M16 signal engine into the two strategy consumers — regime classification gains an A/D-line breadth fallback (`gather_inputs` "ad_line" + `classify_breadth` fallback), and coverage revisions gain a compact per-ticker strategy-signals block in the prompt — without breaking either subsystem's never-raises contract.

**Architecture:** The regime side threads one new input, `ad_line` (the 20d slope of the cumulative `BreadthDaily.net_ad` A/D line, read from the P1 engine's `compute_market_signals()` so signal math stays single-sourced in `apps.market`), through `gather_inputs` → `_classify` → `classify_breadth`, which uses it only when live `$ADVN`/`$DECN` quotes are absent — no sixth axis, no `_RISK_ON`/`_RISK_OFF` change. The coverage side appends `_signals_block(ticker, profile)` (families routed by `profile.strategy_tags`, empty → all) to `_build_prompt` in both diff and full modes, wrapped so any exception collapses to `""`.

**Tech Stack:** Django 5 / Python 3.13, pytest + pytest-django (`monkeypatch`, `unittest.mock.patch`), the P1 signals engine (`apps/market/services/signals/`). No new models, no migrations, no new beat tasks, no FE work in this phase.

**Spec:** docs/superpowers/specs/2026-07-05-strategy-signals-design.md (§8.3, §9, §12)

## Global Constraints

Repo global constraints (from the pinned M16 interface contract — verbatim):

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

Phase-specific constraints (P5):

- **HARD DEPENDENCY: P1 must be merged first.** This phase imports
  `apps.market.services.signals.engine.compute_signals`, `...engine.compute_market_signals`, and
  `apps.market.services.signals.bundles.FAMILY_FOR_TAG`. Before Task 1, verify:
  `docker compose exec web python -c "from apps.market.services.signals.engine import compute_signals, compute_market_signals; from apps.market.services.signals.bundles import FAMILY_FOR_TAG; print('ok')"`
  must print `ok`. If it fails, STOP — do not stub the engine.
- **Soft dependency: P2** adds `TradingProfile.strategy_tags`. All P5 code reads it via
  `getattr(profile, "strategy_tags", None) or []` and all unit tests use `SimpleNamespace`, so P5
  builds and tests green with or without P2; real tag routing only activates once P2 is merged.
- **`gather_inputs` NEVER raises** — every source is try/except-isolated; a missing feed blanks
  exactly one axis (module docstring, `backend/apps/strategy/regime/services/inputs.py:1-2`).
- **`revise_coverage` NEVER raises** — no key / cap / undecryptable cred / AI error / signal-engine
  error all degrade; a raising signals block would break observer fires despite the caller's outer
  `contextlib.suppress` (subsystem-map gotcha). Task 5 proves this with a test.
- **`classify_*` functions are total** — None/empty inputs → `"Unknown"`, never an exception.
- **NO sixth regime axis.** `_RISK_ON` / `_RISK_OFF` (classify.py:90-103) and
  `COMPOSITE_RISK_ON`/`COMPOSITE_RISK_OFF` (constants.py:29-30) are untouched — the ±2 composite
  thresholds are tuned for five axes.
- **No new axis labels.** The fallback emits only the existing breadth vocabulary
  (`Broad`/`Narrow`/`Mixed`/`Unknown`; never `Deteriorating` — that needs a live `$TRIN`), so
  `detect_breadth_divergence` (string-matches `"Deteriorating"`) and `regime_fit` keep working.
- **Shared signal math lives in `apps.market`, not inline in strategy** (subsystem-map gotcha) —
  `gather_inputs` consumes `compute_market_signals()` rather than re-deriving the slope from
  `BreadthDaily` rows.
- `RegimeReading.inputs` is a schemaless JSONField — the new `ad_line` key persists with **no
  migration**. `make check-migrations` must stay green with zero new migration files.
- Expected post-deploy blip (accepted, no action): the first reading after deploy may list
  `breadth` in `changed_axes` when the fallback newly classifies a previously-Unknown axis.
- After merge, restart the long-running services or they run stale code:
  `docker compose restart worker beat`.

---

### Task 1: `classify_breadth` A/D-line fallback + threshold constants

**Files:**
- Modify: `backend/apps/strategy/regime/constants.py` (insert after line 20, `TRIN_DETERIORATING = 2.0`)
- Modify: `backend/apps/strategy/regime/services/classify.py` (function `classify_breadth`, lines 49-62)
- Test: `backend/apps/strategy/regime/tests/test_classify.py` (append at end of file)

**Interfaces:**
- Consumes: nothing from other tasks (pure functions + constants only).
- Produces (Tasks 2/3 rely on these exact names):
  - `apps.strategy.regime.constants.AD_LINE_SLOPE_BROAD: float = 200.0`
  - `apps.strategy.regime.constants.AD_LINE_SLOPE_NARROW: float = -200.0`
  - `classify_breadth(breadth: dict, ad_line: float | None = None) -> str` — live `$ADVN`/`$DECN`
    path is byte-identical to today and wins whenever present; when live quotes are absent
    (either key `None`, or `advn + decn == 0`) the label comes from `ad_line`:
    `None → "Unknown"`, `>= AD_LINE_SLOPE_BROAD → "Broad"`, `<= AD_LINE_SLOPE_NARROW → "Narrow"`,
    else `"Mixed"`. The fallback can never produce `"Deteriorating"`.
  - Private helper `_classify_ad_line(ad_line: float | None) -> str` in classify.py (same rules).

**Steps:**

- [ ] Append the failing truth-table tests to the END of `backend/apps/strategy/regime/tests/test_classify.py`:

```python
@pytest.mark.parametrize(
    "breadth,ad_line,expected",
    [
        # live $ADVN/$DECN present -> live path wins, ad_line is ignored entirely
        ({"$ADVN": 2000, "$DECN": 800}, -500.0, "Broad"),
        ({"$ADVN": 800, "$DECN": 2000}, 500.0, "Narrow"),
        ({"$ADVN": 1500, "$DECN": 1000, "$TRIN": 2.5}, 500.0, "Deteriorating"),
        # live absent -> A/D-line slope fallback
        ({}, None, "Unknown"),
        ({}, 300.0, "Broad"),
        ({}, 200.0, "Broad"),  # boundary: >= AD_LINE_SLOPE_BROAD
        ({}, 199.9, "Mixed"),
        ({}, 0.0, "Mixed"),
        ({}, -199.9, "Mixed"),
        ({}, -200.0, "Narrow"),  # boundary: <= AD_LINE_SLOPE_NARROW
        ({}, -300.0, "Narrow"),
        # partial / degenerate live data also falls back
        ({"$ADVN": None, "$DECN": 1000}, 250.0, "Broad"),
        ({"$ADVN": 0, "$DECN": 0}, -250.0, "Narrow"),
        # the fallback can NEVER produce Deteriorating (that needs a live $TRIN)
        ({"$TRIN": 5.0}, -5000.0, "Narrow"),
    ],
)
def test_classify_breadth_ad_line_fallback(breadth, ad_line, expected):
    assert c.classify_breadth(breadth, ad_line) == expected


def test_classify_breadth_single_arg_stays_backward_compatible():
    # every existing single-arg call site keeps working (ad_line defaults to None)
    assert c.classify_breadth({}) == "Unknown"
    assert c.classify_breadth({"$ADVN": 2000, "$DECN": 800}) == "Broad"
```

- [ ] Run the new tests — they must FAIL:
  `docker compose exec web pytest apps/strategy/regime/tests/test_classify.py -k ad_line -v`
  Expected: 14 parametrized failures with
  `TypeError: classify_breadth() takes 1 positional argument but 2 were given`
  (`test_classify_breadth_single_arg_stays_backward_compatible` passes — that is fine).
- [ ] Add the constants to `backend/apps/strategy/regime/constants.py`. Directly after line 20
  (`TRIN_DETERIORATING = 2.0`), inside the "Breadth" block, insert:

```python
# Breadth fallback: 20d slope of the cumulative A/D line (net advancing issues per
# session, from BreadthDaily via the signals engine). Consulted by classify_breadth
# ONLY when live $ADVN/$DECN quotes are absent (no Schwab). Tunable.
AD_LINE_SLOPE_BROAD = 200.0
AD_LINE_SLOPE_NARROW = -200.0
```

- [ ] Replace `classify_breadth` in `backend/apps/strategy/regime/services/classify.py`
  (lines 49-62). The old body:

```python
def classify_breadth(breadth: dict) -> str:
    advn = breadth.get("$ADVN")
    decn = breadth.get("$DECN")
    trin = breadth.get("$TRIN")
    if advn is None or decn is None or (advn + decn) == 0:
        return UNKNOWN
    if trin is not None and trin >= C.TRIN_DETERIORATING:
        return "Deteriorating"
    ratio = advn / (advn + decn)
    if ratio >= C.BREADTH_BROAD:
        return "Broad"
    if ratio <= C.BREADTH_NARROW:
        return "Narrow"
    return "Mixed"
```

  becomes:

```python
def classify_breadth(breadth: dict, ad_line: float | None = None) -> str:
    advn = breadth.get("$ADVN")
    decn = breadth.get("$DECN")
    trin = breadth.get("$TRIN")
    if advn is None or decn is None or (advn + decn) == 0:
        return _classify_ad_line(ad_line)
    if trin is not None and trin >= C.TRIN_DETERIORATING:
        return "Deteriorating"
    ratio = advn / (advn + decn)
    if ratio >= C.BREADTH_BROAD:
        return "Broad"
    if ratio <= C.BREADTH_NARROW:
        return "Narrow"
    return "Mixed"


def _classify_ad_line(ad_line: float | None) -> str:
    """Fallback breadth read: 20d slope of the cumulative A/D line, used only when
    live $ADVN/$DECN quotes are absent. Total (None -> Unknown) and can never
    produce "Deteriorating" — that requires a live $TRIN."""
    if ad_line is None:
        return UNKNOWN
    if ad_line >= C.AD_LINE_SLOPE_BROAD:
        return "Broad"
    if ad_line <= C.AD_LINE_SLOPE_NARROW:
        return "Narrow"
    return "Mixed"
```

- [ ] Run the whole classify suite (old + new) — all must PASS:
  `docker compose exec web pytest apps/strategy/regime/tests/test_classify.py -v`
  Expected: every test passes, including the pre-existing
  `test_classify_breadth[...]` cases (live path unchanged).
- [ ] Commit:
  `git add backend/apps/strategy/regime/constants.py backend/apps/strategy/regime/services/classify.py backend/apps/strategy/regime/tests/test_classify.py && git commit -m "feat(strategy): classify_breadth falls back to the A/D-line slope when live quotes are absent"`

---

### Task 2: Drivers line marks A/D-line-sourced breadth

**Files:**
- Modify: `backend/apps/strategy/regime/services/classify.py` (function `build_drivers`, lines 122-144 pre-Task-1; after Task 1 it sits below the new `_classify_ad_line` — locate by name)
- Test: `backend/apps/strategy/regime/tests/test_classify.py` (append at end of file)

**Interfaces:**
- Consumes (from Task 1): `classify_breadth(breadth, ad_line=None)` guard semantics — "live absent"
  means `advn is None or decn is None or (advn + decn) == 0`. The drivers helper must mirror that
  guard EXACTLY so the annotation can never disagree with the classification source.
- Produces (Task 3's compute-level test relies on this): `build_drivers(axes, inp)` renders the
  breadth driver as `"breadth <label> (A/D line)"` when the label came from the fallback (live
  quotes absent in `inp["breadth"]` AND `inp["ad_line"]` is not None); the live-sourced driver
  string `"breadth <label>"` is unchanged. Signature of `build_drivers` is unchanged.
  Private helper `_breadth_via_ad_line(inp: dict) -> bool`.

**Steps:**

- [ ] Append the failing tests to the END of `backend/apps/strategy/regime/tests/test_classify.py`:

```python
def test_build_drivers_marks_ad_line_fallback_breadth():
    axes = {
        "volatility": "Unknown",
        "trend": "Unknown",
        "breadth": "Broad",
        "leadership": "Unknown",
        "rates": "Unknown",
    }
    inp = {"breadth": {}, "ad_line": 300.0}
    assert "breadth Broad (A/D line)" in c.build_drivers(axes, inp)


def test_build_drivers_live_breadth_stays_unmarked():
    axes = {
        "volatility": "Unknown",
        "trend": "Unknown",
        "breadth": "Broad",
        "leadership": "Unknown",
        "rates": "Unknown",
    }
    inp = {"breadth": {"$ADVN": 2000, "$DECN": 800}, "ad_line": 300.0}
    drivers = c.build_drivers(axes, inp)
    assert "breadth Broad" in drivers
    assert "breadth Broad (A/D line)" not in drivers
```

- [ ] Run them — they must FAIL:
  `docker compose exec web pytest apps/strategy/regime/tests/test_classify.py -k build_drivers -v`
  Expected: `test_build_drivers_marks_ad_line_fallback_breadth` FAILS with
  `AssertionError: assert 'breadth Broad (A/D line)' in ['breadth Broad']`;
  the other two build_drivers tests pass.
- [ ] Edit `build_drivers` in `backend/apps/strategy/regime/services/classify.py`. The loop body:

```python
        if axis == "leadership":
            drivers.append(f"{label} leadership")
        else:
            drivers.append(f"{prefix} {label}")
```

  becomes:

```python
        if axis == "leadership":
            drivers.append(f"{label} leadership")
        elif axis == "breadth" and _breadth_via_ad_line(inp):
            drivers.append(f"breadth {label} (A/D line)")
        else:
            drivers.append(f"{prefix} {label}")
```

  and directly BELOW the `build_drivers` function, add:

```python
def _breadth_via_ad_line(inp: dict) -> bool:
    """True when the breadth axis came from the A/D-line fallback — mirrors the
    live-quotes guard in classify_breadth exactly."""
    b = inp.get("breadth") or {}
    advn, decn = b.get("$ADVN"), b.get("$DECN")
    live_absent = advn is None or decn is None or (advn + decn) == 0
    return live_absent and inp.get("ad_line") is not None
```

- [ ] Run the full classify suite — all PASS:
  `docker compose exec web pytest apps/strategy/regime/tests/test_classify.py -v`
  Expected: all pass, including the pre-existing `test_build_drivers_skips_unknown`.
- [ ] Commit:
  `git add backend/apps/strategy/regime/services/classify.py backend/apps/strategy/regime/tests/test_classify.py && git commit -m "feat(strategy): mark A/D-line-sourced breadth in regime drivers"`

---

### Task 3: `gather_inputs` "ad_line" key + `_classify` threading

**Files:**
- Modify: `backend/apps/strategy/regime/services/inputs.py` (import block lines 8-12; `out` initializer lines 43-52; new try/except before `return out` at line 81)
- Modify: `backend/apps/strategy/regime/services/compute.py` (function `_classify`, line 30)
- Tests: `backend/apps/strategy/regime/tests/test_inputs.py` (append), `backend/apps/strategy/regime/tests/test_compute.py` (append)

**Interfaces:**
- Consumes (P1 contract — these names are law):
  `apps.market.services.signals.engine.compute_market_signals() -> dict[str, float | None]`,
  never raises, returns market-wide signals including key `"ad_line_slope_20d"` (20d slope of the
  cumulative `BreadthDaily.net_ad` A/D line; `None` when history is insufficient).
- Consumes (Task 1): `classify_breadth(breadth, ad_line=None)`.
- Consumes (Task 2): drivers string `"breadth <label> (A/D line)"`.
- Produces: `gather_inputs()` dict gains key `"ad_line": float | None` (default `None`), filled in
  its own isolated try/except from `(compute_market_signals() or {}).get("ad_line_slope_20d")` —
  None-safe against a misbehaving engine returning `None`. `compute._classify` threads
  `inp.get("ad_line")` as the second positional arg to `classify_breadth`. The key persists into
  `RegimeReading.inputs` automatically (schemaless JSONField — no migration).

**Steps:**

- [ ] Append the failing tests to the END of `backend/apps/strategy/regime/tests/test_inputs.py`:

```python
def test_gather_inputs_ad_line_from_engine(monkeypatch):
    monkeypatch.setattr(I, "fetch_market_context", lambda: {"vix_last": 15.0, "breadth": {}})
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})
    monkeypatch.setattr(I, "compute_market_signals", lambda: {"ad_line_slope_20d": 123.4})
    out = I.gather_inputs()
    assert out["ad_line"] == 123.4


def test_gather_inputs_ad_line_failure_is_isolated(monkeypatch):
    monkeypatch.setattr(
        I,
        "fetch_market_context",
        lambda: {"vix_last": 22.0, "breadth": {"$ADVN": 1500, "$DECN": 900}},
    )
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})

    def boom():
        raise RuntimeError("engine down")

    monkeypatch.setattr(I, "compute_market_signals", boom)
    out = I.gather_inputs()  # must not raise
    assert out["ad_line"] is None
    assert out["vix_last"] == 22.0  # other sources unaffected — isolation holds


def test_gather_inputs_ad_line_none_return_is_safe(monkeypatch):
    monkeypatch.setattr(I, "fetch_market_context", lambda: {"vix_last": 15.0, "breadth": {}})
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})
    monkeypatch.setattr(I, "compute_market_signals", lambda: None)  # misbehaving engine
    out = I.gather_inputs()
    assert out["ad_line"] is None
```

- [ ] Run them — they must FAIL:
  `docker compose exec web pytest apps/strategy/regime/tests/test_inputs.py -k ad_line -v`
  Expected: 3 failures with
  `AttributeError: <module 'apps.strategy.regime.services.inputs' ...> has no attribute 'compute_market_signals'`
  (monkeypatch cannot set a name the module never imported).
- [ ] Append the failing compute-level test to the END of
  `backend/apps/strategy/regime/tests/test_compute.py`:

```python
AD_FALLBACK_INPUTS = {
    "vix_last": 12.0,
    "vix_percentile": 0.2,
    "spx_ma_spread": 4.0,
    "spx_dist_50": 3.0,
    "breadth": {},  # no Schwab -> no live A/D quotes
    "ad_line": 300.0,  # engine-supplied cumulative A/D-line 20d slope
    "sector_returns": {},
    "t10y2y": 0.5,
    "tnx_change": -0.03,
}


def test_ad_line_fallback_classifies_breadth_axis(monkeypatch):
    monkeypatch.setattr(compute, "regime_narrative", lambda *a, **k: "")
    monkeypatch.setattr(compute, "gather_inputs", lambda: AD_FALLBACK_INPUTS)
    reading = compute.compute_and_store()
    assert reading.axes["breadth"] == "Broad"
    assert "breadth Broad (A/D line)" in reading.drivers
    assert reading.inputs["ad_line"] == 300.0  # schemaless JSONField persists the new key
```

- [ ] Run it — it must FAIL:
  `docker compose exec web pytest apps/strategy/regime/tests/test_compute.py::test_ad_line_fallback_classifies_breadth_axis -v`
  Expected: `AssertionError: assert 'Unknown' == 'Broad'` (`_classify` does not thread `ad_line` yet).
- [ ] Edit `backend/apps/strategy/regime/services/inputs.py`. In the import block, after
  `from apps.market.services.fred import fetch_macro` (line 10), insert:

```python
from apps.market.services.signals.engine import compute_market_signals
```

  In the `gather_inputs` `out` initializer (lines 43-52), after `"breadth": {},` insert:

```python
        "ad_line": None,
```

  And directly before the final `return out` (after the macro try/except block ending at line 80),
  insert this isolated block:

```python
    try:
        # Engine-sourced (single source of signal math): 20d slope of the cumulative
        # BreadthDaily A/D line. `or {}` guards a misbehaving engine returning None.
        out["ad_line"] = (compute_market_signals() or {}).get("ad_line_slope_20d")
    except Exception:
        log.warning("regime.inputs.ad_line_failed", exc_info=True)
```

- [ ] Edit `backend/apps/strategy/regime/services/compute.py` line 30. The `_classify` entry:

```python
        "breadth": classify_breadth(inp.get("breadth") or {}),
```

  becomes:

```python
        "breadth": classify_breadth(inp.get("breadth") or {}, inp.get("ad_line")),
```

- [ ] Run BOTH full files (the pre-existing `test_inputs.py` tests do not patch
  `compute_market_signals`, so they now exercise the real engine — it never raises per the P1
  contract and returns `None`-valued signals on an empty DB, so they must stay green):
  `docker compose exec web pytest apps/strategy/regime/tests/test_inputs.py apps/strategy/regime/tests/test_compute.py -v`
  Expected: all pass (3 new + 1 new + all pre-existing).
- [ ] Commit:
  `git add backend/apps/strategy/regime/services/inputs.py backend/apps/strategy/regime/services/compute.py backend/apps/strategy/regime/tests/test_inputs.py backend/apps/strategy/regime/tests/test_compute.py && git commit -m "feat(strategy): gather ad_line regime input from the signals engine"`

---

### Task 4: Coverage `_signals_block(ticker, profile)`

**Files:**
- Modify: `backend/apps/strategy/coverage/services/revise.py` (import block lines 21-30; new functions appended after `_format_prior` at end of file, currently line 157)
- Create test: `backend/apps/strategy/coverage/tests/test_signals_block.py`

**Interfaces:**
- Consumes (P1 contract — these names are law):
  - `apps.market.services.signals.engine.compute_signals(ticker: str, families: list[str] | None = None, *, benchmark: str = "$SPX") -> dict[str, dict[str, float | int | str | None]]` — `{family: {signal_name: value|None}}`, never raises, `families=None` means all four.
  - `apps.market.services.signals.bundles.FAMILY_FOR_TAG: dict[str, str]` (tag → family; identity today).
- Consumes (P2, soft): `profile.strategy_tags` — read defensively via
  `getattr(profile, "strategy_tags", None) or []` so pre-P2 profiles route to all families.
- Produces (Task 5 relies on these exact names/behaviors):
  - `_signals_block(ticker: str, profile) -> str` in
    `apps.strategy.coverage.services.revise` — compact text starting
    `"Current strategy signals for {ticker}:"` with one `- {family}: name=value, ...` line per
    family; `None`-valued signals are dropped (absent, never invented); floats render `:.2f`;
    unknown/empty tags → `families=None` (all four); **any exception → returns `""`** (and the
    all-`None` case also returns `""`). Tests patch it via the module-bound name
    `apps.strategy.coverage.services.revise.compute_signals`.
  - `_fmt_signal(value: object) -> str` private formatter.

**Steps:**

- [ ] Create `backend/apps/strategy/coverage/tests/test_signals_block.py` (pure unit — no DB):

```python
"""P5 unit tests: the compact strategy-signals block for the coverage prompt.

``compute_signals`` is patched at the name bound in the revise module — the same
convention test_revise.py uses for ``run_structured``. Profiles are stand-ins
(SimpleNamespace): ``_signals_block`` only reads ``strategy_tags``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from apps.strategy.coverage.services.revise import _signals_block

SIGNALS_PATCH = "apps.strategy.coverage.services.revise.compute_signals"

FAKE_SIGNALS = {
    "momentum": {"macd_hist": 1.234, "adx": 27.5, "rs_vs_spx": None},
    "mean_reversion": {"zscore_20d": -2.1},
}


def _profile(tags):
    return SimpleNamespace(strategy_tags=tags)


def test_signals_block_formats_families_compactly():
    with patch(SIGNALS_PATCH, return_value=FAKE_SIGNALS):
        block = _signals_block("SPY", _profile([]))
    assert block.startswith("Current strategy signals for SPY:")
    assert "- momentum: macd_hist=1.23, adx=27.50" in block
    assert "- mean_reversion: zscore_20d=-2.10" in block
    assert "rs_vs_spx" not in block  # None signals are dropped — absent, never invented


def test_signals_block_routes_families_from_strategy_tags():
    with patch(SIGNALS_PATCH, return_value={"momentum": {"adx": 20.0}}) as cs:
        _signals_block("SPY", _profile(["momentum"]))
    cs.assert_called_once_with("SPY", ["momentum"])


def test_signals_block_empty_tags_means_all_families():
    with patch(SIGNALS_PATCH, return_value=FAKE_SIGNALS) as cs:
        _signals_block("SPY", _profile([]))
    cs.assert_called_once_with("SPY", None)


def test_signals_block_unknown_tags_fall_back_to_all_families():
    with patch(SIGNALS_PATCH, return_value=FAKE_SIGNALS) as cs:
        _signals_block("SPY", _profile(["not-a-tag"]))
    cs.assert_called_once_with("SPY", None)


def test_signals_block_missing_strategy_tags_attr_means_all_families():
    # pre-P2 TradingProfile has no strategy_tags field at all
    with patch(SIGNALS_PATCH, return_value=FAKE_SIGNALS) as cs:
        _signals_block("SPY", SimpleNamespace())
    cs.assert_called_once_with("SPY", None)


def test_signals_block_exception_returns_empty_string():
    with patch(SIGNALS_PATCH, side_effect=RuntimeError("engine down")):
        assert _signals_block("SPY", _profile([])) == ""


def test_signals_block_all_none_returns_empty_string():
    with patch(SIGNALS_PATCH, return_value={"momentum": {"adx": None, "macd_hist": None}}):
        assert _signals_block("SPY", _profile([])) == ""
```

- [ ] Run it — it must FAIL at collection:
  `docker compose exec web pytest apps/strategy/coverage/tests/test_signals_block.py -v`
  Expected: `ImportError: cannot import name '_signals_block' from 'apps.strategy.coverage.services.revise'`.
- [ ] Edit `backend/apps/strategy/coverage/services/revise.py`. In the import block, after
  `from apps.ai.providers.claude_structured import run_structured` (line 23), insert (isort order:
  `apps.market` sorts between `apps.ai` and `apps.secrets`):

```python
from apps.market.services.signals.bundles import FAMILY_FOR_TAG
from apps.market.services.signals.engine import compute_signals
```

  Then append at the END of the file, after `_format_prior`:

```python
def _signals_block(ticker: str, profile) -> str:
    """Compact strategy-signal readout appended to the revision prompt.

    Families follow ``profile.strategy_tags`` (empty/unknown -> all four).
    Best-effort: ANY failure returns "" so ``revise_coverage`` keeps its
    never-raises contract — a broken signal engine must not break the observer
    fire that triggered the revision.
    """
    try:
        tags = list(getattr(profile, "strategy_tags", None) or [])
        families = [FAMILY_FOR_TAG[t] for t in tags if t in FAMILY_FOR_TAG] or None
        signals = compute_signals(ticker, families)
        lines = []
        for family, values in signals.items():
            parts = [
                f"{name}={_fmt_signal(value)}"
                for name, value in values.items()
                if value is not None
            ]
            if parts:
                lines.append(f"- {family}: " + ", ".join(parts))
        if not lines:
            return ""
        return f"Current strategy signals for {ticker}:\n" + "\n".join(lines)
    except Exception:
        log.warning("coverage: signals block failed for %s", ticker, exc_info=True)
        return ""


def _fmt_signal(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
```

- [ ] Run the new file plus the existing revise suite (proves no regression from the new imports):
  `docker compose exec web pytest apps/strategy/coverage/tests/test_signals_block.py apps/strategy/coverage/tests/test_revise.py -v`
  Expected: all pass (7 new + 6 pre-existing).
- [ ] Commit:
  `git add backend/apps/strategy/coverage/services/revise.py backend/apps/strategy/coverage/tests/test_signals_block.py && git commit -m "feat(strategy): add a strategy-signals block builder for coverage revisions"`

---

### Task 5: `_build_prompt` appends the block in BOTH modes + never-raise proof

**Files:**
- Modify: `backend/apps/strategy/coverage/services/revise.py` (call site line 72 `user=_build_prompt(...)`; function `_build_prompt`, lines 126-147)
- Create test: `backend/apps/strategy/coverage/tests/test_prompt_signals.py`

**Interfaces:**
- Consumes (Task 4): `_signals_block(ticker, profile) -> str` (`""` on any failure; module-bound
  patch name `apps.strategy.coverage.services.revise.compute_signals`; block text starts
  `"Current strategy signals for {ticker}:"`).
- Consumes (existing code, unchanged): `revise_coverage(ticker, snapshot, *, profile)` at
  revise.py:35 — never raises, `profile` already in scope; `run_structured` is called with
  keyword args (`user=...`), patched in tests at
  `apps.strategy.coverage.services.revise.run_structured`;
  `previous_snapshot_for(snapshot)` (apps/snapshots/primary.py:29) returns the most-recent prior
  READY snapshot sharing `snapshot.primary_ticker` — `Snapshot.captured_at` is `auto_now_add`, so
  tests backdate the prior row via queryset `.update(captured_at=...)`.
- Produces:
  - `_build_prompt(note: CoverageNote, snapshot, ticker: str, provider_name: str, model_id: str, profile) -> str`
    — new trailing `profile` parameter; the signals block is inserted between the
    `"New information:"` section and the `"Revise the house view ONLY if..."` instructions, in
    BOTH the diff mode (prior snapshot exists) and the full-serialize mode; an empty block
    inserts nothing (no stray blank lines).
  - The `revise_coverage` → `_build_prompt` call site passes `profile`.

**Steps:**

- [ ] Create `backend/apps/strategy/coverage/tests/test_prompt_signals.py`:

```python
"""P5 tests: the signals block reaches the coverage prompt in BOTH modes, and a
raising signal engine can never break ``revise_coverage`` (never-raises contract
— a raising block would break observer fires despite the caller's suppress).

``run_structured`` / ``compute_signals`` are patched at the names bound in the
revise module (the convention documented in test_revise.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.strategy.coverage.schemas import CoverageRevisionDraft
from apps.strategy.coverage.services.revise import _build_prompt, revise_coverage
from apps.strategy.models import CoverageNote

pytestmark = pytest.mark.django_db

SIGNALS_PATCH = "apps.strategy.coverage.services.revise.compute_signals"
AI_PATCH = "apps.strategy.coverage.services.revise.run_structured"

FAKE_SIGNALS = {"momentum": {"adx": 27.5}}


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s", default_provider="claude")


@pytest.fixture
def provider_cfg(db) -> ProviderConfig:
    cfg = ProviderConfig.objects.create(
        provider="claude", enabled=True, default_model="claude-opus-4-8"
    )
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


def _snapshot(profile) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile, status="ready", primary_ticker="SPY", source="manual"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"SPY": {"last": 525.0}}
    )
    return snap


def _note() -> CoverageNote:
    return CoverageNote.objects.create(ticker="SPY", stance="neutral", conviction=2)


def test_prompt_contains_signals_block_full_mode(profile):
    note, snap = _note(), _snapshot(profile)  # no prior snapshot -> full-serialize mode
    with patch(SIGNALS_PATCH, return_value=FAKE_SIGNALS):
        prompt = _build_prompt(note, snap, "SPY", "claude", "m", SimpleNamespace(strategy_tags=[]))
    assert "Changes since snapshot #" not in prompt  # proves full mode
    assert "Current strategy signals for SPY:" in prompt
    assert "- momentum: adx=27.50" in prompt


def test_prompt_contains_signals_block_diff_mode(profile):
    prev = _snapshot(profile)
    # captured_at is auto_now_add (create-time values ignored) -> backdate via update()
    Snapshot.objects.filter(pk=prev.pk).update(
        captured_at=timezone.now() - timezone.timedelta(hours=1)
    )
    note, curr = _note(), _snapshot(profile)
    with patch(SIGNALS_PATCH, return_value=FAKE_SIGNALS):
        prompt = _build_prompt(note, curr, "SPY", "claude", "m", SimpleNamespace(strategy_tags=[]))
    assert f"Changes since snapshot #{prev.id}:" in prompt  # proves diff mode
    assert "Current strategy signals for SPY:" in prompt


def test_prompt_omits_block_on_engine_failure(profile):
    note, snap = _note(), _snapshot(profile)
    with patch(SIGNALS_PATCH, side_effect=RuntimeError("engine down")):
        prompt = _build_prompt(note, snap, "SPY", "claude", "m", SimpleNamespace(strategy_tags=[]))
    assert "Current strategy signals" not in prompt
    assert "Revise the house view ONLY if" in prompt  # the prompt is otherwise intact


def _draft() -> CoverageRevisionDraft:
    return CoverageRevisionDraft(
        material_change=True,
        stance="bull",
        conviction=3,
        bull_case="upside",
        bear_case="downside",
        key_levels={"support": 520.0},
        watching_for="CPI print",
        reason="r",
    )


def test_raising_engine_never_breaks_revise_coverage(profile, provider_cfg):
    snap = _snapshot(profile)
    with (
        patch(SIGNALS_PATCH, side_effect=RuntimeError("engine down")),
        patch(AI_PATCH, return_value=_draft()) as ai,
    ):
        rev = revise_coverage("SPY", snap, profile=profile)  # must not raise
    assert rev is not None  # the revision still happened — signals are additive, never load-bearing
    assert "Current strategy signals" not in ai.call_args.kwargs["user"]
```

- [ ] Run it — it must FAIL:
  `docker compose exec web pytest apps/strategy/coverage/tests/test_prompt_signals.py -v`
  Expected: 4 collected — the three `_build_prompt` tests FAIL with
  `TypeError: _build_prompt() takes 5 positional arguments but 6 were given`, and
  `test_raising_engine_never_breaks_revise_coverage` PASSES vacuously (the block is not wired
  into `revise_coverage` yet, so nothing raises and nothing leaks into the prompt).
- [ ] Edit `backend/apps/strategy/coverage/services/revise.py`. Replace `_build_prompt`
  (lines 126-147). The old function:

```python
def _build_prompt(
    note: CoverageNote, snapshot, ticker: str, provider_name: str, model_id: str
) -> str:
    """Prior house view + the current situation — a compact diff vs the prior
    snapshot when one exists, else the full serialized payload."""
    prev = previous_snapshot_for(snapshot)
    if prev is not None:
        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in snapshot.sections.all()}
        delta = diff_sections(prev_sections, curr_sections)
        situation = f"Changes since snapshot #{prev.id}:\n{delta}"
    else:
        situation = serialize_for_ai(snapshot, provider=provider_name, model=model_id)

    return (
        f"You maintain a standing house view on {ticker}. The current view:\n\n"
        f"{_format_prior(note)}\n\n"
        f"New information:\n{situation}\n\n"
        "Revise the house view ONLY if something material changed. If nothing "
        "material did, set material_change=false and reaffirm the existing view "
        "unchanged. Always explain your reasoning in `reason`."
    )
```

  becomes:

```python
def _build_prompt(
    note: CoverageNote, snapshot, ticker: str, provider_name: str, model_id: str, profile
) -> str:
    """Prior house view + the current situation — a compact diff vs the prior
    snapshot when one exists, else the full serialized payload — plus a compact
    strategy-signals block (both modes; "" on any signal failure)."""
    prev = previous_snapshot_for(snapshot)
    if prev is not None:
        prev_sections = {s.kind: s.payload for s in prev.sections.all()}
        curr_sections = {s.kind: s.payload for s in snapshot.sections.all()}
        delta = diff_sections(prev_sections, curr_sections)
        situation = f"Changes since snapshot #{prev.id}:\n{delta}"
    else:
        situation = serialize_for_ai(snapshot, provider=provider_name, model=model_id)

    signals = _signals_block(ticker, profile)
    signals_part = f"{signals}\n\n" if signals else ""
    return (
        f"You maintain a standing house view on {ticker}. The current view:\n\n"
        f"{_format_prior(note)}\n\n"
        f"New information:\n{situation}\n\n"
        f"{signals_part}"
        "Revise the house view ONLY if something material changed. If nothing "
        "material did, set material_change=false and reaffirm the existing view "
        "unchanged. Always explain your reasoning in `reason`."
    )
```

  And update the call site inside `revise_coverage` (line 72). The old line:

```python
            user=_build_prompt(note, snapshot, ticker, provider_name, model_id),
```

  becomes:

```python
            user=_build_prompt(note, snapshot, ticker, provider_name, model_id, profile),
```

- [ ] Run the whole coverage suite — all must PASS (test_revise.py exercises `revise_coverage`
  end-to-end and now transits the real `_signals_block`; `compute_signals` never raises per the
  P1 contract, so those tests stay green):
  `docker compose exec web pytest apps/strategy/coverage/tests/ -v`
  Expected: all pass (4 new + everything pre-existing in test_revise.py / test_api.py /
  test_observer_hook.py / test_signals_block.py).
- [ ] Commit:
  `git add backend/apps/strategy/coverage/services/revise.py backend/apps/strategy/coverage/tests/test_prompt_signals.py && git commit -m "feat(strategy): append the signals block to the coverage prompt in both modes"`

---

### Task 6: Phase verification — full suite, lint, no-migration gate

**Files:**
- No source changes expected. Fix-forward only if a gate reds; any fix must show its own diff and be committed with a `fix(strategy):` message.

**Interfaces:**
- Consumes: everything Tasks 1-5 produced. Nothing produced — this task is the phase gate.

**Steps:**

- [ ] Run the entire strategy app suite plus the two adjacent suites the phase touched indirectly:
  `docker compose exec web pytest apps/strategy/ -v`
  Expected: all pass, zero skips beyond pre-existing ones.
- [ ] Confirm P5 introduced NO model change and NO migration:
  `make check-migrations`
  Expected: exits 0 ("No changes detected" — `RegimeReading.inputs` is a schemaless JSONField;
  `ad_line` needed no migration). Also `git status --short backend/apps/*/migrations/` prints
  nothing.
- [ ] Confirm no beat/task/flag inventory drift was needed (P5 adds no tasks or flags — the drift
  gates must pass untouched):
  `docker compose exec web pytest apps/core/tests/test_celery_registration.py -v`
  Expected: all pass with `apps/core/scheduled_tasks.py` unmodified by this phase
  (`git diff --stat main -- backend/apps/core/` prints nothing).
- [ ] Run the full lint gate:
  `make lint`
  Expected: ruff / mypy / import-linter / deptry / semgrep-rules all green (`ty` advisory noise is
  acceptable). `apps.strategy` importing `apps.market.services.signals` follows the existing
  `returns.py` allowance — if import-linter reds here, the contract file's allowance for P1 was
  not landed; STOP and report rather than editing contracts.
- [ ] Run the two touched suites once more under the CI determinism profile:
  `docker compose exec web pytest apps/strategy/regime/tests/ apps/strategy/coverage/tests/ -p no:randomly -q`
  Expected: all pass.
- [ ] Restart the long-running services so the worker (runs `coverage.revise_from_observation`)
  and beat (schedules `strategy.regime_refresh`) pick up the new code — the stale-worker landmine:
  `docker compose restart worker beat`
  Expected: both containers restart healthy (`docker compose ps` shows `running`).
- [ ] Commit only if a fix was needed during this task; otherwise nothing to commit. Final state:
  `git log --oneline -5` shows the four `feat(strategy):` commits from Tasks 1-5.
