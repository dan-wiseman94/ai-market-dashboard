# Snapshot Macro-Desk Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 16-category snapshot coverage gaps — richer defaults, render the computed-but-discarded signals, add credit spreads/VVIX/dollar/factor returns/history depth through existing providers, and ship the `fed` + `flowlite` sections and Form 4 insider filings.

**Architecture:** Everything flows through the existing capture pipeline — `_FETCHERS` registry → `SnapshotSection.payload` → `serialize_for_ai` renderers → `token_budget` pruning. New data rides existing provider calls (one batched Schwab/fallback quote, the FRED `SERIES` dict, stored `OHLCBar` rows); the only new fetch surface is the keyless Fed RSS service. No new apps, tasks, or dependencies.

**Tech Stack:** Django 6 / DRF / Celery (existing), `requests` for the Fed feeds, stdlib `xml.etree`, React 19 + TS for the include pickers.

**Spec:** `docs/superpowers/specs/2026-09-19-snapshot-macro-desk-coverage-design.md` — read it first; every task cites its section. **Workstream E (TradingView symbol-map rows) is NOT in this plan** — it lands as a small follow-up plan after the `worktree-tradingview-mcp` branch merges (its target dicts don't exist on this branch yet).

## Global Constraints

- Branch: `worktree-snapshot-macro-desk` (worktree at `.claude/worktrees/snapshot-macro-desk`, based on main `b8c351ba`). Commit with `LEFTHOOK=0 git commit …` (the worktree has no lefthook binary).
- **Test execution from the worktree** (the main stack mounts the main checkout, not this tree): use the untracked `compose.worktree.yaml` overlay already present here. `DC="docker compose -f compose.yaml -f compose.worktree.yaml -p macrodesk"`; once: `$DC up -d db redis`; then `$DC run --rm --no-deps -T web uv run pytest apps/<app>/tests/test_<x>.py -v` (WORKDIR is `/app/backend` — no `backend/` prefix), `$DC run --rm --no-deps -T frontend pnpm exec vitest run <path>`, `$DC run --rm --no-deps -T web uv run python manage.py makemigrations --check --dry-run`, `$DC run --rm --no-deps -T -w /app/backend web uv run python manage.py spectacular --file schema.yml --validate`, and `$DC run --rm --no-deps -T --entrypoint "" -w /app web uv run ruff check backend/apps/<app>` (any `-w /app` run needs `--entrypoint ""`). Where a step says `docker compose exec web …`, use the matching `$DC run --rm --no-deps -T web …` form. When done: `$DC down -v`.
- `SnapshotSection.kind` strings are **≤16 chars** (`max_length=16`). New section kinds touch five surfaces: `_FETCHERS`, `KIND_CHOICES` + migration, `_title` + `_RENDERERS`, and the FE include lists (CLAUDE.md → "Adding a snapshot section kind").
- `TradingProfile.save()` seeds `default_includes` only when **empty** — constant changes need the Task 15 data migration to reach existing profiles.
- Never set `MOCK_EXTERNAL` on the dev stack. Never log provider keys; errors via `safe_log.safe_err`.
- Sections must never raise out of their fetcher for degradable conditions — return empty shapes; only a truly-failed fetch propagates (the capture loop marks the section `failed`).
- Conventional commits (`feat(market):` etc.) with the session's attribution footer. Run `ruff check`/`ruff format` on touched backend files before each commit.
- Section payloads JSON-round-trip: **int dict keys come back as strings** — renderers must tolerate both (see the existing `relative_strength` comment in `serializer.py`).

---

### Task 1: FRED credit-spread series (spec C1)

**Files:**
- Modify: `backend/apps/market/services/fred.py` (the `SERIES` dict, lines ~28–44)
- Test: `backend/apps/market/tests/test_fred.py` (extend; if the file doesn't exist, create it with just these tests)

**Interfaces:**
- Produces: two new `SERIES` entries — `"BAMLH0A0HYM2": "HY OAS"`, `"BAMLC0A0CM": "IG OAS"`. `fetch_macro` iterates `SERIES` generically and `_render_macro` iterates `series.values()` generically, so no other code changes.

- [ ] **Step 1: Write the failing test**

```python
def test_series_includes_credit_spread_oas_rows():
    from apps.market.services.fred import SERIES

    assert SERIES["BAMLH0A0HYM2"] == "HY OAS"
    assert SERIES["BAMLC0A0CM"] == "IG OAS"
    # The macro fetch iterates SERIES generically — the dict IS the contract.
    assert list(SERIES) == list(dict.fromkeys(SERIES))  # no dup keys
```

- [ ] **Step 2: Run to verify it fails** — `$DC run --rm --no-deps -T web uv run pytest apps/market/tests/test_fred.py -v` → FAIL (`KeyError: 'BAMLH0A0HYM2'`).

- [ ] **Step 3: Implement** — in the `SERIES` dict, after the `"T10Y2Y": "10Y-2Y spread",` entry add:

```python
    "BAMLH0A0HYM2": "HY OAS",
    "BAMLC0A0CM": "IG OAS",
```

- [ ] **Step 4: Run the whole module's tests** — `… pytest apps/market/tests/test_fred.py -v` → PASS (existing per-series tests prove the generic iteration is unaffected).

- [ ] **Step 5: Commit** — `feat(market): add HY/IG OAS credit-spread FRED series`

---

### Task 2: VVIX in the always-on vix section (spec C2)

**Files:**
- Modify: `backend/apps/market/services/vix.py` (`vix_term_structure`), `backend/apps/snapshots/serializer.py` (`_render_vix`)
- Test: `backend/apps/market/tests/test_vix.py`, `backend/apps/snapshots/tests/` (the existing vix-render test module)

**Interfaces:**
- Produces: payload keys `vvix: {"symbol": "$VVIX", "last", "pct_change"} | None` and `vvix_vix_ratio: float | None`. The section's raise condition is **unchanged** — missing VVIX can never fail the section.

- [ ] **Step 1: Write the failing tests** (in `test_vix.py`; mirror the module's existing `monkeypatch`-on-`vix.fetch_quotes` pattern):

```python
import datetime as dt

def _q(last, pct=1.0):
    return {"last": last, "pct_change": pct}

def _syms(today):
    from apps.market.services import vix
    (front_sym, _), (second_sym, _) = vix.front_and_second(today)
    return front_sym, second_sym

def test_vvix_rides_the_batched_quote(monkeypatch):
    from apps.market.services import vix
    today = dt.date(2026, 9, 18)
    front_sym, second_sym = _syms(today)
    seen: dict = {}
    quotes = {"$VIX": _q(15.0), "$VVIX": _q(90.0), front_sym: _q(16.0), second_sym: _q(17.0)}
    monkeypatch.setattr(vix, "fetch_quotes", lambda syms: seen.setdefault("syms", list(syms)) and quotes or quotes)
    payload = vix.vix_term_structure(today=today)
    assert "$VVIX" in seen["syms"]                      # one batch, no extra call
    assert payload["vvix"] == {"symbol": "$VVIX", "last": 90.0, "pct_change": 1.0}
    assert payload["vvix_vix_ratio"] == 6.0

def test_missing_vvix_never_fails_the_section(monkeypatch):
    from apps.market.services import vix
    today = dt.date(2026, 9, 18)
    front_sym, second_sym = _syms(today)
    quotes = {"$VIX": _q(15.0), front_sym: _q(16.0), second_sym: _q(17.0)}
    monkeypatch.setattr(vix, "fetch_quotes", lambda syms: quotes)
    payload = vix.vix_term_structure(today=today)
    assert payload["vvix"] is None and payload["vvix_vix_ratio"] is None
    assert payload["front"] is not None                 # rest of the section intact
```

- [ ] **Step 2: Run to verify failure** — `… pytest apps/market/tests/test_vix.py -v` → the new tests FAIL (`KeyError: 'vvix'`).

- [ ] **Step 3: Implement in `vix_term_structure`** (all anchors are verbatim on this branch):
  1. Batch: `quotes = fetch_quotes(["$VIX", "$VVIX", "/VX", front_sym, second_sym])`.
  2. After `second_q = _usable(quotes.get(second_sym))` add: `vvix_q = _usable(quotes.get("$VVIX"))`.
  3. In the `payload` dict, after the `"spot"` entry add:

```python
        "vvix": (
            {"symbol": "$VVIX", "last": vvix_q.get("last"), "pct_change": vvix_q.get("pct_change")}
            if vvix_q is not None
            else None
        ),
        "vvix_vix_ratio": None,
```

  4. After the contango block (before the `note` logic) add:

```python
    spot_last_v = (payload["spot"] or {}).get("last")
    vvix_last = (payload["vvix"] or {}).get("last")
    if isinstance(vvix_last, int | float) and isinstance(spot_last_v, int | float) and spot_last_v:
        payload["vvix_vix_ratio"] = _round(vvix_last / spot_last_v)
```

  5. In the `payload["front"] is None` branch, replace the note assignment with:

```python
        payload["note"] = (
            "VIX futures and VVIX unavailable (requires Schwab connection)"
            if payload["vvix"] is None
            else "VIX futures unavailable (requires Schwab connection)"
        )
```

- [ ] **Step 4: Render** — in `serializer.py::_render_vix`, immediately after the spot line is appended, add (adapt only the accumulator name if it isn't `lines`):

```python
    vvix = payload.get("vvix")
    if isinstance(vvix, dict) and vvix.get("last") is not None:
        ratio = payload.get("vvix_vix_ratio")
        ratio_s = f" — VVIX/VIX {float(ratio):.2f}" if isinstance(ratio, int | float) else ""
        lines.append(f"- VVIX: {_fmt(vvix.get('last'))} ({_fmt(vvix.get('pct_change'))}%){ratio_s}")
```

Add one render test in the snapshots vix-render test module: a payload with `vvix` renders a `- VVIX: 90.00` line; a payload with `vvix=None` renders no VVIX line.

- [ ] **Step 5: Run** — `… pytest apps/market/tests/test_vix.py apps/snapshots/tests -k vix -v` → PASS.

- [ ] **Step 6: Commit** — `feat(market): quote $VVIX in the always-on vix section`

---

### Task 3: intel breadth-stats + factor returns (spec C5, C6)

**Files:**
- Modify: `backend/apps/market/services/intel.py`
- Test: `backend/apps/market/tests/test_intel.py` (extend the existing module; it already seeds `OHLCBar` rows for `sector_rotation` tests — reuse its fixture helper)

**Interfaces:**
- Produces (Task 4 and Task 6 consume these exact signatures):
  - `factor_returns(etfs: list[str], *, windows: tuple[int, ...] = (1, 5, 20)) -> dict | None` returning `{"windows": [1,5,20], "etfs": {ETF: {w: pct|None}}, "spreads": {"momentum_minus_value"|"small_minus_large"|"growth_minus_value_proxy": {w: pct|None}}}`.
  - `breadth_stats(tickers: list[str], *, sma_periods: tuple[int, ...] = (20, 50), hl_window: int = 252) -> dict | None` returning `{"pct_above_sma": {period: {"above", "n", "pct"}}, "highs", "lows", "hl_n", "hl_window", "min_span_sessions"}`.

- [ ] **Step 1: Write the failing tests** (seed daily bars the way the module's existing tests do; the essential cases):

```python
def test_factor_returns_shape_and_spreads(db, seed_daily_bars):
    # seed: MTUM +10% over 5 sessions, VLUE +2%, IWM +1%, SPY +3%, QQQ +5%
    from apps.market.services.intel import factor_returns
    out = factor_returns(["MTUM", "VLUE", "QUAL", "USMV", "IWM", "SPY"])
    assert out["windows"] == [1, 5, 20]
    assert out["etfs"]["MTUM"][5] is not None
    assert out["spreads"]["momentum_minus_value"][5] == round(
        out["etfs"]["MTUM"][5] - out["etfs"]["VLUE"][5], 4
    )
    assert out["etfs"]["QUAL"][5] is None            # unseeded leg → honest None

def test_factor_returns_none_when_no_bars(db):
    from apps.market.services.intel import factor_returns
    assert factor_returns(["MTUM", "VLUE"]) is None

def test_breadth_stats_counts_and_real_window(db, seed_daily_bars):
    # seed 60 bars for 4 tickers; one closes at its span high, one at its span low
    from apps.market.services.intel import breadth_stats
    out = breadth_stats(["XLK", "XLF", "XLE", "XLV"])
    assert out["pct_above_sma"][20]["n"] == 4
    assert out["highs"] == 1 and out["lows"] == 1
    assert out["min_span_sessions"] == 60            # labels the REAL window, not 252

def test_breadth_stats_none_when_thin(db):
    from apps.market.services.intel import breadth_stats
    assert breadth_stats(["XLK"]) is None
```

(`seed_daily_bars` = whatever bar-seeding fixture/helper `test_intel.py` already uses; extend it rather than inventing a second one.)

- [ ] **Step 2: Run to verify failure** — `… pytest apps/market/tests/test_intel.py -v` → FAIL (`ImportError`).

- [ ] **Step 3: Implement** — append to `intel.py`:

```python
FACTOR_SPREADS: tuple[tuple[str, str, str], ...] = (
    ("momentum_minus_value", "MTUM", "VLUE"),
    ("small_minus_large", "IWM", "SPY"),
    ("growth_minus_value_proxy", "QQQ", "SPY"),
)


def factor_returns(etfs: list[str], *, windows: tuple[int, ...] = (1, 5, 20)) -> dict | None:
    """Per-ETF returns over each window plus long-short style spreads.

    Stored 1d bars only; an ETF with thin bars gets None per window, a spread
    with a missing leg is None, and the whole result is None when nothing has
    a value (honest coverage, same contract as sector_rotation)."""
    etf_rows: dict[str, dict[int, float | None]] = {}
    any_value = False
    for etf in etfs:
        row = {w: return_over_sessions(etf, w) for w in windows}
        any_value = any_value or any(v is not None for v in row.values())
        etf_rows[etf.upper()] = row
    if not any_value:
        return None
    spreads: dict[str, dict[int, float | None]] = {}
    for name, long_leg, short_leg in FACTOR_SPREADS:
        spreads[name] = {}
        for w in windows:
            lo = return_over_sessions(long_leg, w)
            sh = return_over_sessions(short_leg, w)
            spreads[name][w] = round(lo - sh, 4) if lo is not None and sh is not None else None
    return {"windows": list(windows), "etfs": etf_rows, "spreads": spreads}


def _closes(ticker: str, limit: int) -> list[float]:
    return [
        float(b.close)
        for b in OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d").order_by("-ts")[
            :limit
        ]
    ]


def breadth_stats(
    tickers: list[str],
    *,
    sma_periods: tuple[int, ...] = (20, 50),
    hl_window: int = 252,
) -> dict | None:
    """% of tickers above their N-session SMA + fresh high/low counts.

    The high/low span clamps to the bars actually stored (retention prunes at
    ~400 calendar days); min_span_sessions reports the smallest span used so
    the render can label the REAL window. None when < 3 tickers usable."""
    sma: dict[int, dict] = {}
    for period in sma_periods:
        above = total = 0
        for t in tickers:
            closes = _closes(t, period)
            if len(closes) < period:
                continue
            total += 1
            if closes[0] > sum(closes) / len(closes):
                above += 1
        sma[period] = {
            "above": above,
            "n": total,
            "pct": round(above / total * 100, 1) if total else None,
        }
    highs = lows = counted = 0
    min_span: int | None = None
    for t in tickers:
        closes = _closes(t, hl_window)
        if len(closes) < 20:
            continue
        counted += 1
        min_span = len(closes) if min_span is None else min(min_span, len(closes))
        last, rest = closes[0], closes[1:]
        if rest and last >= max(rest):
            highs += 1
        if rest and last <= min(rest):
            lows += 1
    if counted < 3:
        return None
    return {
        "pct_above_sma": sma,
        "highs": highs,
        "lows": lows,
        "hl_n": counted,
        "hl_window": hl_window,
        "min_span_sessions": min_span,
    }
```

- [ ] **Step 4: Run** — `… pytest apps/market/tests/test_intel.py -v` → PASS. `ruff check`/`format`.

- [ ] **Step 5: Commit** — `feat(market): intel breadth_stats + factor_returns off stored daily bars`

---

### Task 4: context payload — sector pct, dollar, index complex, up/down volume (spec B1-data, C3, C4, C6)

**Files:**
- Modify: `backend/apps/market/services/context.py`
- Test: `backend/apps/market/tests/test_context.py`

**Interfaces:**
- Consumes: `intel.factor_returns` / `intel.breadth_stats` (Task 3 signatures).
- Produces (Task 6's renderer consumes): payload keys `sector_pct: {ETF: pct}`, `dollar: {"symbol","last","pct_change"}|None`, `index_complex: [{"symbol","last","pct_change"}]`, `factor_returns: dict|None`, `breadth_stats: dict|None`; `breadth` may now carry `$UVOL`/`$DVOL`. Constants `INDEX_COMPLEX`, `FUTURES_COMPLEX`, `FACTOR_ETFS`.

- [ ] **Step 1: Write the failing tests** (call `_fetch` directly — it bypasses the Redis cache; patch `context.fetch_quotes`):

```python
def _quotes(**overrides):
    base = {s: {"last": 100.0, "pct_change": 0.5} for s in
            ["$SPX", "QQQ", "$VIX", "SPY", "UUP", "XLK", "XLF", "XLE", "XLV", "XLY",
             "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]}
    base["$ADVN"] = {"last": 2000}; base["$DECN"] = {"last": 900}
    base["$UVOL"] = {"last": 5.1e9}; base["$DVOL"] = {"last": 2.2e9}
    base.update(overrides)
    return base

def test_fetch_carries_sector_pct_dollar_and_index_complex(monkeypatch, db):
    from apps.market.services import context
    calls = []
    def fake_fetch(symbols):
        calls.append(sorted(symbols))
        return {"/ES": {"last": 6500.0, "pct_change": 0.3}, "/NQ": {"last": 24000.0, "pct_change": 0.4}} \
            if any(s.startswith("/") for s in symbols) else _quotes()
    monkeypatch.setattr(context, "fetch_quotes", fake_fetch)
    p = context._fetch(None)
    assert p["sector_pct"]["XLK"] == 0.5
    assert p["dollar"]["symbol"] == "UUP"
    assert [r["symbol"] for r in p["index_complex"]] == ["$SPX", "SPY", "QQQ", "/ES", "/NQ"]
    assert p["breadth"]["$UVOL"] == 5.1e9
    assert len(calls) == 2                     # futures fetched in their OWN call

def test_rejected_futures_call_cannot_blank_the_etf_batch(monkeypatch, db):
    from apps.market.services import context
    def fake_fetch(symbols):
        if any(s.startswith("/") for s in symbols):
            raise RuntimeError("provider rejected /ES")
        return _quotes()
    monkeypatch.setattr(context, "fetch_quotes", fake_fetch)
    p = context._fetch(None)
    assert p["sectors"]["XLK"] == 100.0        # ETF batch intact
    assert [r["symbol"] for r in p["index_complex"]] == ["$SPX", "SPY", "QQQ"]
```

- [ ] **Step 2: Run to verify failure** — `… pytest apps/market/tests/test_context.py -v` → FAIL (`KeyError: 'sector_pct'`).

- [ ] **Step 3: Implement** — in `context.py`:
  1. Constants (replace `BREADTH` and `CONTEXT_SYMBOLS`; keep `MACRO` — it is NOT dead, `ingest_daily_bars` builds its universe from `MACRO.values()`):

```python
INDEX_COMPLEX = ["$SPX", "SPY", "QQQ"]
# Futures go in a SEPARATE quote call: Alpaca's fallback is one whole-batch
# request that returns {} for the entire batch when any symbol is rejected —
# a bad /ES must not blank the ETF rows.
FUTURES_COMPLEX = ["/ES", "/NQ"]
FACTOR_ETFS = ["MTUM", "VLUE", "QUAL", "USMV", "IWM", "SPY"]
# $UVOL/$DVOL ride the same try-and-see contract as the A/D indices.
BREADTH = ["$ADVN", "$DECN", "$TICK", "$TRIN", "$UVOL", "$DVOL"]
CONTEXT_SYMBOLS = CORE + ["SPY", "UUP"] + SECTOR_ETFS + BREADTH
```

  2. Row helper (module level):

```python
def _row(quotes: dict, sym: str) -> dict | None:
    q = quotes.get(sym) or {}
    if q.get("last") is None:
        return None
    return {"symbol": sym, "last": q.get("last"), "pct_change": q.get("pct_change")}
```

  3. In `_fetch`, after the existing `rotation` try/except, add three more best-effort blocks (same shape/logging as the existing ones): `futures_quotes = fetch_quotes(FUTURES_COMPLEX)` (except → `{}`), `factor = intel.factor_returns(FACTOR_ETFS)` (except → `None`), `stats = intel.breadth_stats(SECTOR_ETFS)` (except → `None`).
  4. Extend the returned dict (keep every existing key):

```python
        "sector_pct": {
            etf: pc for etf in SECTOR_ETFS
            if (pc := quotes.get(etf, {}).get("pct_change")) is not None
        },
        "dollar": _row(quotes, "UUP"),
        "index_complex": [
            row for sym in INDEX_COMPLEX + FUTURES_COMPLEX
            if (row := _row({**quotes, **futures_quotes}, sym)) is not None
        ],
        "factor_returns": factor,
        "breadth_stats": stats,
```

  The `_internals` warm-up gate is untouched — it already iterates `BREADTH`, so `$UVOL`/`$DVOL` ride in and stay gated behind `advn + decn >= 100`.

- [ ] **Step 4: Run** — `… pytest apps/market/tests/test_context.py apps/market/tests/test_intel.py -v` → PASS. Also run the snapshots serializer tests (`… pytest apps/snapshots -k breadth -v`) — the old renderer must still pass untouched (new keys are additive).

- [ ] **Step 5: Commit** — `feat(market): context carries sector pct, dollar, index complex, factor + breadth stats`

---

### Task 5: 52-week history depth (spec C7)

**Files:**
- Modify: `backend/apps/market/tasks.py` (`ingest_daily_bars`), `backend/apps/market/services/fallback.py` (`alt_bars`), `backend/apps/market/services/polygon.py` (`fetch_daily_bars` params)
- Test: `backend/apps/market/tests/test_fallback.py`, `backend/apps/market/tests/test_tasks.py` (or the module holding `ingest_daily_bars` tests)

**Interfaces:**
- Produces: nightly universe fetch at `bars=260`; `alt_bars` converts a bar count to a calendar-day lookback (`int(limit * 1.45) + 5`) for Tiingo/Polygon; Polygon's aggregates `limit` param becomes `500`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ingest_daily_bars_requests_260(monkeypatch, db):
    from apps.market import tasks
    seen = []
    monkeypatch.setattr(
        "apps.market.services.ohlc.fetch_ohlc",
        lambda sym, *, timeframe, bars: seen.append((sym, timeframe, bars)) or [],
    )
    tasks.ingest_daily_bars()
    assert seen and all(b == 260 for _, _, b in seen)

def test_alt_bars_converts_bar_count_to_calendar_days_for_tiingo(monkeypatch):
    from apps.market.services import fallback
    monkeypatch.setattr(fallback, "_has", lambda name: name == "tiingo")
    seen = {}
    monkeypatch.setattr(
        "apps.market.services.tiingo.fetch_daily_bars",
        lambda ticker, *, days: seen.setdefault("days", days) or [],
    )
    fallback.alt_bars("SPY", timeframe="1d", limit=260)
    assert seen["days"] == int(260 * 1.45) + 5    # ≈382 calendar days → ~260 trading bars
```

Add the twin test for the polygon branch, and one asserting `polygon.fetch_daily_bars` sends `"limit": 500` (patch the module's `_get`, capture `params`).

- [ ] **Step 2: Run to verify failure** — bars assertion fails at 60; days assertion fails at 260.

- [ ] **Step 3: Implement**
  1. `tasks.py::ingest_daily_bars`: `fetch_ohlc(sym, timeframe="1d", bars=60)` → `bars=260`, and update the task docstring's last line to note the 52-week depth feeds `breadth_stats`/the ohlc summary.
  2. `fallback.py::alt_bars`: in the Tiingo and Polygon branches replace `days=limit` with:

```python
        # These providers treat the count as a CALENDAR-day lookback, not a bar
        # count (260 days ≈ 178 trading bars) — convert so 260 bars means 260 bars.
        days = int(limit * 1.45) + 5
```

  and pass `days=days`.
  3. `polygon.py`: `params = {"adjusted": "false", "sort": "asc", "limit": 120}` → `"limit": 500` (the aggregates row cap must cover 260 trading bars).

- [ ] **Step 4: Run** — `… pytest apps/market/tests/test_fallback.py apps/market/tests -k "ingest or polygon" -v` → PASS.

- [ ] **Step 5: Commit** — `feat(market): ingest 52 weeks of daily bars (260) with true bar-count fallbacks`

---

### Task 6: breadth renderer overhaul (spec B1-render + C3/C4/C5/C6 render)

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (`_render_breadth`, currently lines ~376–413)
- Test: the snapshots serializer test module that covers `_render_breadth`

**Interfaces:**
- Consumes: Task 4's payload keys verbatim (`index_complex`, `dollar`, `sector_pct`, `factor_returns`, `breadth_stats`) — all optional, all may arrive JSON-round-tripped (int keys as strings).

- [ ] **Step 1: Write the failing tests**

```python
def _breadth_payload():
    return {
        "spx_last": 6500.0, "qqq_last": 560.0, "vix_last": 15.0,
        "index_complex": [
            {"symbol": "$SPX", "last": 6500.0, "pct_change": 0.4},
            {"symbol": "/ES", "last": 6510.0, "pct_change": 0.5},
        ],
        "dollar": {"symbol": "UUP", "last": 27.9, "pct_change": -0.2},
        "sectors": {"XLK": 231.4, "XLF": 45.1},
        "sector_pct": {"XLK": 1.2},
        "sector_rotation": [{"sector": "XLK", "return_pct": 2.5, "rs": 1.1}],
        "breadth": {"$ADVN": 2000, "$DECN": 900, "$UVOL": 5.1e9, "$DVOL": 2.2e9},
        "breadth_stats": {"pct_above_sma": {"20": {"above": 7, "n": 11, "pct": 63.6}},
                          "highs": 2, "lows": 1, "hl_n": 11, "hl_window": 252,
                          "min_span_sessions": 60},
        "relative_strength": None,
        "factor_returns": {"windows": [1, 5, 20],
                           "etfs": {"MTUM": {"5": 4.0}, "VLUE": {"5": 1.0}},
                           "spreads": {"momentum_minus_value": {"5": 3.0}}},
    }

def test_render_breadth_full_desk_view():
    from apps.snapshots.serializer import _render_breadth
    out = _render_breadth(_breadth_payload())
    assert "- Index complex: $SPX 6500.00 (0.40%), /ES 6510.00 (0.50%)" in out
    assert "- Dollar (UUP): 27.90 (-0.20%)" in out
    assert "| XLK | 231.40 | 1.20 | 2.50 | 1.10 |" in out         # sector table row
    assert "$UVOL" in out                                          # internals line
    assert ">20dSMA 64% (7/11)" in out
    assert "≤60-session span" in out                               # real window, not 252
    assert "MTUM +4.00%" in out and "Mom-Val +3.00%" in out

def test_render_breadth_without_new_keys_still_renders():
    from apps.snapshots.serializer import _render_breadth
    out = _render_breadth({"spx_last": 6500.0, "qqq_last": 560.0, "vix_last": 15.0})
    assert "- SPX: 6500.00" in out and "- VIX: 15.00" in out       # old payloads intact
```

- [ ] **Step 2: Run to verify failure** — `… pytest apps/snapshots -k breadth -v` → the new tests FAIL.

- [ ] **Step 3: Implement** — replace the body of `_render_breadth` with:

```python
def _render_breadth(payload: dict) -> str:
    lines = ["## Market breadth"]
    idx = payload.get("index_complex") or []
    if idx:
        bits = ", ".join(
            f"{r['symbol']} {_fmt(r.get('last'))} ({_fmt(r.get('pct_change'))}%)" for r in idx
        )
        lines.append(f"- Index complex: {bits}")
    else:
        lines.append(f"- SPX: {_fmt(payload.get('spx_last'))}")
        lines.append(f"- QQQ: {_fmt(payload.get('qqq_last'))}")
    lines.append(f"- VIX: {_fmt(payload.get('vix_last'))}")
    dollar = payload.get("dollar")
    if isinstance(dollar, dict):
        lines.append(
            f"- Dollar (UUP): {_fmt(dollar.get('last'))} ({_fmt(dollar.get('pct_change'))}%)"
        )
    sectors = payload.get("sectors") or {}
    if sectors:
        pct = payload.get("sector_pct") or {}
        rot = {r["sector"]: r for r in (payload.get("sector_rotation") or [])}
        lines += ["", "| Sector | Last | 1d% | 5d% | RS vs SPX (5d) |", "|---|---:|---:|---:|---:|"]
        for etf, last in sectors.items():
            r = rot.get(etf) or {}
            lines.append(
                f"| {etf} | {_fmt(last)} | {_fmt(pct.get(etf))} | "
                f"{_fmt(r.get('return_pct'))} | {_fmt(r.get('rs'))} |"
            )
        lines.append("")
    if payload.get("breadth"):
        lines.append(
            "- Internals: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["breadth"].items())
        )
    stats = payload.get("breadth_stats")
    if isinstance(stats, dict):
        sma_bits = [
            f">{p}dSMA {d['pct']:.0f}% ({d['above']}/{d['n']})"
            for p, d in (stats.get("pct_above_sma") or {}).items()
            if isinstance(d, dict) and d.get("pct") is not None
        ]
        if sma_bits:
            lines.append("- Sector breadth: " + ", ".join(sma_bits))
        if stats.get("hl_n"):
            span = stats.get("min_span_sessions") or stats.get("hl_window")
            lines.append(
                f"- Fresh highs/lows (≤{span}-session span, {stats['hl_n']} names): "
                f"{stats.get('highs', 0)} high / {stats.get('lows', 0)} low"
            )
    # Relative strength — keys may be int or str after a JSON round-trip.
    rs = payload.get("relative_strength")
    if rs and rs.get("windows"):
        bits = []
        for w, d in rs["windows"].items():
            if d.get("rs") is not None:
                bits.append(f"{w}d {d['rs']:+.2f}%")
        if bits:
            lines.append(
                f"- Relative strength ({rs['ticker']} vs {rs['benchmark']}): " + ", ".join(bits)
            )
    factor = payload.get("factor_returns")
    if isinstance(factor, dict):
        def _w5(row: dict):
            v = row.get(5, row.get("5"))
            return v if isinstance(v, int | float) else None
        etf_bits = [
            f"{etf} {v:+.2f}%"
            for etf, row in (factor.get("etfs") or {}).items()
            if (v := _w5(row)) is not None
        ]
        if etf_bits:
            lines.append("- Factor ETFs (5d): " + ", ".join(etf_bits))
        sp_labels = (
            ("Mom-Val", "momentum_minus_value"),
            ("Small-Large", "small_minus_large"),
            ("Growth-Value", "growth_minus_value_proxy"),
        )
        sp_bits = [
            f"{label} {v:+.2f}%"
            for label, key in sp_labels
            if (v := _w5((factor.get("spreads") or {}).get(key) or {})) is not None
        ]
        if sp_bits:
            lines.append("- Factor spreads (5d): " + ", ".join(sp_bits))
    return "\n".join(lines)
```

(The leader/laggard sector-rotation line is deliberately replaced by the table — spec B1 gap (3).)

- [ ] **Step 4: Run** — `… pytest apps/snapshots -k breadth -v` → PASS; run the FULL snapshots test module to catch any golden-text assertions on the old sector/rotation lines and update them to the new render.

- [ ] **Step 5: Commit** — `feat(snapshots): breadth renders sector table, index complex, dollar, factor + breadth stats`

---

### Task 7: chain render — GEX by strike, top OI/volume, unusual activity (spec B2, B3, B4)

**Files:**
- Modify: `backend/apps/market/services/option_analytics.py` (`_gex`), `backend/apps/snapshots/serializer.py` (`_render_chain`, `_render_chain_analytics`, and the chain call site in `serialize_for_ai`)
- Test: `backend/apps/market/tests/test_option_analytics.py`, snapshots chain-render tests, plus a query-budget test

**Interfaces:**
- Produces: `_gex` return gains `"by_strike": [{"strike": float, "gex": float}]` (top 6 by |GEX|, strike-ascending; `[]` in the two degrade returns). `_render_chain` gains a `captured_at: datetime | None = None` keyword.
- Consumes: `apps.analytics.services.unusual_options.unusual_options(*, ticker, at, top_n=25)` — **keyword-only**.

- [ ] **Step 1: Write the failing tests**

```python
def test_gex_reports_top_strikes():
    from apps.market.services.option_analytics import _gex
    contracts = [
        {"side": "call", "strike": 100, "gamma": "0.05", "oi": "1000"},
        {"side": "put", "strike": 95, "gamma": "0.04", "oi": "2000"},
        {"side": "call", "strike": 105, "gamma": "0.01", "oi": "100"},
    ]
    out = _gex(contracts, spot=100.0)
    strikes = [r["strike"] for r in out["by_strike"]]
    assert strikes == sorted(strikes)                 # ascending for the render
    assert {r["strike"] for r in out["by_strike"]} == {95.0, 100.0, 105.0}
    assert out["by_strike"][0]["gex"] < 0             # 95 put wall is negative

def test_gex_degrade_returns_carry_empty_by_strike():
    from apps.market.services.option_analytics import _gex
    assert _gex([], spot=None)["by_strike"] == []
    assert _gex([], spot=100.0)["by_strike"] == []
```

Snapshots side (chain-render test module): a rendered chain payload with two expiries asserts the render contains `- GEX by strike`, a `**Top volume strikes**` line, and — with `unusual_options` patched to return one flagged row — an `**Unusual activity:**` block; with it patched to raise, the render still returns (no crash). Query-budget test: wrap one full chain render in `django_assert_max_num_queries(3)`.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `option_analytics._gex`** — add `"by_strike": []` to both early returns, and before the final return:

```python
    top = sorted(strike_gex.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6]
    by_strike = [
        {"strike": k, "gex": round(v, 2)} for k, v in sorted(top, key=lambda kv: kv[0])
    ]
```

and include `"by_strike": by_strike,` in the returned dict.

- [ ] **Step 4: Implement the render additions** in `serializer.py`:
  1. `_render_chain_analytics` — after the existing GEX line:

```python
    by_strike = gex.get("by_strike") or []
    if by_strike:
        walls = ", ".join(f"{_fmt(r['strike'])}: {r['gex']:,.0f}" for r in by_strike)
        parts.append(f"- GEX by strike (top {len(by_strike)}, gamma walls): {walls}")
```

  2. `_render_chain` — signature becomes `def _render_chain(payload: dict, *, ticker: str = "?", captured_at=None) -> str:`. After the analytics block (which already builds the `flat` contract list), add:

```python
    def _sf(v) -> float:
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    def _top(side: str, key: str) -> str:
        rows = sorted(
            (c for c in flat if c.get("side") == side and _sf(c.get(key)) > 0),
            key=lambda c: _sf(c.get(key)),
            reverse=True,
        )[:5]
        return ", ".join(
            f"{c.get('strike')} ({c.get('expiry')}) {int(_sf(c.get(key))):,}" for c in rows
        )

    for label, key in (("volume", "volume"), ("OI", "oi")):
        calls_s, puts_s = _top("call", key), _top("put", key)
        if calls_s or puts_s:
            lines.append(f"\n**Top {label} strikes** — calls: {calls_s or '—'} | puts: {puts_s or '—'}")
```

  3. Unusual activity (same function, after the top-strikes block). First read `apps/analytics/services/unusual_options.py` for the flagged-row keys (strike/side/expiry + the reason field) and render those exact keys:

```python
    if captured_at is not None and ticker not in ("?", "", None):
        try:
            from apps.analytics.services.unusual_options import unusual_options

            flagged = unusual_options(ticker=ticker, at=captured_at, top_n=5)
        except Exception:
            flagged = []
        if flagged:
            lines.append("\n**Unusual activity:**")
            for row in flagged:
                lines.append(f"- {_describe_unusual(row)}")
```

  with `_describe_unusual(row)` a small serializer helper formatting the confirmed keys (e.g. `"{side} {strike} {expiry}: vol/OI 4.2 — volume 8,400 vs OI 2,000"`).
  4. Call site: find where `serialize_for_ai` invokes the chain renderer with `ticker=` and pass `captured_at=snap.captured_at` (the snapshot object is in scope there; confirm the attribute name used elsewhere in the file).

- [ ] **Step 5: Run** — analytics + snapshots chain tests + the query-budget test → PASS.

- [ ] **Step 6: Commit** — `feat(snapshots): chain render shows gamma walls, top OI/volume strikes, unusual activity`

---

### Task 8: events — seed refresh, detail render, corporate actions (spec C10, B5, C11)

**Files:**
- Modify: `backend/apps/market/services/events_seed.py`, `backend/apps/snapshots/serializer.py` (`_render_events`), `backend/apps/snapshots/services/__init__.py` (the `events` fetcher)
- Test: `backend/apps/market/tests/test_events_service.py` (seed shape), snapshots events-render tests

**Interfaces:**
- Produces: events section payload gains `corporate_actions: [{"ticker","kind","ex_date","ratio","amount"}]` (≤20 rows, 14-day window).

- [ ] **Step 1: Seed refresh (data step — no code semantics change).** Verify release dates with WebFetch against the three sources named in the seed's docstring (federalreserve.gov FOMC calendar; bls.gov news-release schedule; bea.gov schedule), then: (a) extend FOMC/CPI/NFP rows through 2027 in the existing `_row(event, time)` format with correct EDT/EST UTC hours (the docstring's rule); (b) add `_row("Core PCE Price Index", …)` and `_row("GDP Growth Rate", …)` rows for the remaining 2026 + 2027 dates — the `_MACRO_MAP` needles `"pce"`/`"gdp"` already classify these titles (verify in `events.py:110–122`, do NOT add needles). Add a test asserting the seed now contains ≥1 future-dated row for each of the five kinds and that every row's `event` classifies to a kind via `_macro_kind`.

- [ ] **Step 2: Failing render test**

```python
def test_render_events_shows_detail_and_corporate_actions():
    from apps.snapshots.serializer import _render_events
    payload = {
        "earnings": [{"ticker": "NVDA", "days_until": 3, "when_hint": "amc",
                      "detail": {"eps_est": 1.25, "eps_actual": 1.3, "rev_est": 46_000_000_000}}],
        "macro": [{"title": "CPI YoY", "days_until": 5,
                   "detail": {"estimate": 2.9, "prev": 3.1, "actual": None}}],
        "corporate_actions": [{"ticker": "AAPL", "kind": "dividend", "ex_date": "2026-09-26",
                               "ratio": None, "amount": 0.26}],
    }
    out = _render_events(payload)
    assert "est EPS 1.25" in out and "last actual 1.3" in out and "est rev" in out
    assert "CPI YoY in 5d (est 2.9, prev 3.1)" in out
    assert "- AAPL dividend $0.26 ex 2026-09-26" in out
```

- [ ] **Step 3: Implement `_render_events`** — replace the two loops (earnings/macro) and extend the empty-check:

```python
def _render_events(payload) -> str:
    earnings = payload.get("earnings", []) if isinstance(payload, dict) else []
    macro = payload.get("macro", []) if isinstance(payload, dict) else []
    actions = payload.get("corporate_actions", []) if isinstance(payload, dict) else []
    if not earnings and not macro and not actions:
        return "## Upcoming events\n_(none in the next 14 days)_"
    lines = ["## Upcoming events"]
    for e in earnings:
        hint = f", {e['when_hint'].upper()}" if e.get("when_hint") else ""
        d = e.get("detail") or {}
        bits = []
        if d.get("eps_est") is not None:
            bits.append(f"est EPS {d['eps_est']}")
        if d.get("eps_actual") is not None:
            bits.append(f"last actual {d['eps_actual']}")
        if d.get("rev_est") is not None:
            bits.append(f"est rev {d['rev_est']}")
        est_s = f", {', '.join(bits)}" if bits else ""
        lines.append(f"- {e['ticker']} earnings in {e['days_until']}d{hint}{est_s}")
    for m in macro:
        d = m.get("detail") or {}
        extra = ", ".join(
            f"{label} {d[k]}"
            for label, k in (("est", "estimate"), ("prev", "prev"), ("actual", "actual"))
            if d.get(k) is not None
        )
        lines.append(f"- {m['title']} in {m['days_until']}d" + (f" ({extra})" if extra else ""))
    for a in actions:
        what = (
            f"split {a['ratio']}" if a.get("ratio") is not None else f"dividend ${a['amount']}"
        )
        lines.append(f"- {a['ticker']} {what} ex {a['ex_date']}")
    return "\n".join(lines)
```

- [ ] **Step 4: Implement the fetcher** — in `snapshots/services/__init__.py`, replace the `"events"` lambda with a named `_fetch_events_section` beside the other helpers:

```python
def _fetch_events_section(*, watchlist_tickers: list[str], **_) -> dict:
    import datetime as _dt

    from apps.market.models import CorporateAction

    data = upcoming_events(list(watchlist_tickers), within_days=14, include_macro=True)
    today = _dt.date.today()
    data["corporate_actions"] = [
        {
            "ticker": a.ticker,
            "kind": a.kind,
            "ex_date": a.ex_date.isoformat(),
            "ratio": float(a.ratio) if a.ratio is not None else None,
            "amount": float(a.amount) if a.amount is not None else None,
        }
        for a in CorporateAction.objects.filter(
            ticker__in=[t.upper() for t in watchlist_tickers],
            ex_date__gte=today,
            ex_date__lte=today + _dt.timedelta(days=14),
        ).order_by("ex_date")[:20]
    ]
    return {"data": data}
```

  (`upcoming_events` returns the `{"earnings": …, "macro": …}` dict — confirm and keep its call unchanged.) Register `"events": _fetch_events_section` in `_FETCHERS`. Add a fetcher test seeding one future `CorporateAction` row.

- [ ] **Step 5: Run** — events service + snapshots events tests → PASS.

- [ ] **Step 6: Commit** — `feat(snapshots): events carry forecasts, actuals, and the corporate-actions calendar` (seed refresh may be its own preceding `chore(market):` commit).

---

### Task 9: Form 4 insider filings + real filings/treasury renderers (spec 6.3, B6)

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (filings fetcher), `backend/apps/snapshots/serializer.py` (new `_render_filings`, `_render_treasury`, `_title` entries, `_RENDERERS` registration), `backend/apps/secrets/data_sources.py` (verify the EDGAR blurb — it should now be accurate unchanged)
- Test: `backend/apps/market/tests/test_edgar.py`, snapshots render tests

**Interfaces:**
- Produces: filings payload shape per ticker becomes `{"filings": [rows], "insider": [rows]}`; the renderer accepts BOTH this and the legacy flat-list shape (old persisted snapshots re-render).

- [ ] **Step 1: Failing tests** — (a) edgar: the filings fetcher makes a **separate** call for Form 4 (`forms=("4",), limit=5, max_age_days=45`) — patch `edgar_fetch_filings` in the snapshots services module, capture calls, assert two calls per ticker with those kwargs and that the base call's kwargs are unchanged (the shared `limit=10` budget must not be diluted by Form 4s — spec 6.3); (b) render: new-shape payload renders a `### TICKER` block with a `| Form | Filed | Title |` table and an `**Insider activity (Form 4):**` line; legacy flat-list payload still renders the table; treasury payload renders without a raw ` ```json ` fence.

- [ ] **Step 2: Implement the fetcher** — replace the `"filings"` lambda body's dict comprehension value with:

```python
            t: {
                "filings": edgar_fetch_filings(t),
                "insider": edgar_fetch_filings(t, forms=("4",), limit=5, max_age_days=45),
            }
```

- [ ] **Step 3: Implement the renderers** in `serializer.py`:

```python
def _render_filings(payload) -> str:
    if not isinstance(payload, dict) or not payload:
        return "## SEC filings\n_(none)_"
    lines = ["## SEC filings"]
    any_rows = False
    for ticker, entry in payload.items():
        rows = entry.get("filings") if isinstance(entry, dict) else entry
        insider = entry.get("insider", []) if isinstance(entry, dict) else []
        if not rows and not insider:
            continue
        any_rows = True
        lines.append(f"\n### {ticker}")
        if rows:
            lines += ["| Form | Filed | Title |", "|---|---|---|"]
            for f in rows:
                lines.append(
                    f"| {f.get('form')} | {f.get('filed')} | [{f.get('title')}]({f.get('url')}) |"
                )
        if insider:
            lines.append(
                "**Insider activity (Form 4):** "
                + "; ".join(f"{i.get('filed')} [{i.get('title')}]({i.get('url')})" for i in insider)
            )
    return "\n".join(lines) if any_rows else "## SEC filings\n_(none)_"
```

  For `_render_treasury`, read `fetch_treasury`'s returned keys in `backend/apps/market/services/treasury.py` first, then render a two-part block — a `| Security | Avg rate |` table over the rates rows and one `- Debt to the penny: $…` line — using those exact keys; `_(unavailable)_` when empty. Register both in `_RENDERERS` and add `"filings": "SEC filings"`, `"treasury": "Treasury"` to `_title`.

- [ ] **Step 4: data_sources.py** — confirm the EDGAR entry's blurb ("Company filings + Form 4 insider trades. No key required.") is now accurate; change nothing if so.

- [ ] **Step 5: Run** — edgar + snapshots render tests → PASS.

- [ ] **Step 6: Commit** — `feat(snapshots): Form 4 insider filings + real filings/treasury renderers`

---

### Task 10: long-horizon OHLC summary (spec C8)

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (`_render_ohlc` tail + new `_long_horizon_summary`)
- Test: snapshots ohlc-render tests

- [ ] **Step 1: Failing test** — seed ~60 daily `OHLCBar` rows for `"SPY"`, render an ohlc payload with `{"ticker": "SPY", …}`, assert the output contains `**Longer horizon (stored daily bars):**`, a `-session high`, and a `vs 20dSMA` fragment; with no stored bars, assert the block is absent.

- [ ] **Step 2: Implement** — add the helper and call it at the very end of `_render_ohlc` (append its return value to the section text when non-empty; the payload's ticker key is `"ticker"`):

```python
def _long_horizon_summary(ticker: str | None) -> str:
    """52-week context off stored daily bars — the persisted OHLCBar archive
    otherwise never reaches the prompt. Empty string when bars are thin."""
    if not ticker:
        return ""
    from apps.market.models import OHLCBar
    from apps.market.services.intel import return_over_sessions

    closes = [
        float(b.close)
        for b in OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d").order_by("-ts")[
            :252
        ]
    ]
    if len(closes) < 20:
        return ""
    last, hi, lo = closes[0], max(closes), min(closes)
    bits = [
        f"{len(closes)}-session high {hi:.2f} / low {lo:.2f}",
        f"{(last - hi) / hi * 100:+.1f}% off high",
    ]
    for p in (20, 50, 200):
        if len(closes) >= p:
            sma = sum(closes[:p]) / p
            bits.append(f"{(last - sma) / sma * 100:+.1f}% vs {p}dSMA")
    rets = [
        f"{w}d {r:+.1f}%" for w in (5, 20, 60) if (r := return_over_sessions(ticker, w)) is not None
    ]
    if rets:
        bits.append("returns " + ", ".join(rets))
    return "\n\n**Longer horizon (stored daily bars):** " + " | ".join(bits)
```

- [ ] **Step 3: Run** — ohlc render tests → PASS (watch the serializer's existing golden asserts).

- [ ] **Step 4: Commit** — `feat(snapshots): long-horizon summary block in the ohlc render`

---

### Task 11: live curve proxy in the macro render (spec C9)

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (`_render_macro`)
- Test: snapshots macro-render tests

- [ ] **Step 1: Failing test** — a macro payload whose `live_yields` carries `{"13W": {"ticker": "$IRX", "yield_pct": 4.1}, "30Y": {"ticker": "$TYX", "yield_pct": 4.9}}` renders `- Live curve proxy (30Y − 13W): +0.80pp` and a note pointing at the FRED `T10Y2Y` row as the official 2s10s; with either tenor missing, the line is absent.

- [ ] **Step 2: Implement** — in `_render_macro`, after the live-yields table is emitted:

```python
    ly = payload.get("live_yields") or {}
    long_y = (ly.get("30Y") or {}).get("yield_pct")
    short_y = (ly.get("13W") or {}).get("yield_pct")
    if isinstance(long_y, int | float) and isinstance(short_y, int | float):
        lines.append(
            f"- Live curve proxy (30Y − 13W): {long_y - short_y:+.2f}pp "
            f"(official 2s10s is the lagged FRED 10Y-2Y spread row above)"
        )
```

  (Adapt the accumulator name to `_render_macro`'s local; `live_yields` is `{tenor: {"ticker", "yield_pct"}}` per `yields.py::live_yields`.)

- [ ] **Step 3: Run** — macro render tests → PASS.

- [ ] **Step 4: Commit** — `feat(snapshots): live curve-proxy spread in the macro render`

---

### Task 12: `fed` service — Federal Reserve RSS (spec 6.1)

**Files:**
- Create: `backend/apps/market/services/fed.py`
- Modify: `backend/apps/market/cache.py` (add a `"fed": 3600` TTL entry to the kind→TTL table)
- Test: `backend/apps/market/tests/test_fed.py` (new)

**Interfaces:**
- Produces (Task 14 consumes): `fetch_fed_communications(*, limit: int = 10) -> list[dict]` — items `{"kind", "title", "url", "published" (ISO|None), "summary"}`, newest-first, `[]` on any failure, canned items under `MOCK_EXTERNAL`.

- [ ] **Step 1: Verify the feed URLs** (implementation-time check, spec 6.1): confirm `https://www.federalreserve.gov/feeds/press_monetary.xml` plus the speeches and testimony feed paths from `https://www.federalreserve.gov/feeds/` (WebFetch). Use the confirmed URLs in the `FEEDS` dict; drop any feed that doesn't exist.

- [ ] **Step 2: Write the failing tests**

```python
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Federal Reserve issues FOMC statement</title>
<link>https://www.federalreserve.gov/x.htm</link>
<pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate>
<description>Statement text.</description></item>
</channel></rss>"""

def test_parse_extracts_items():
    from apps.market.services.fed import _parse
    items = _parse("press_monetary", RSS)
    assert items[0]["title"].startswith("Federal Reserve issues")
    assert items[0]["published"].startswith("2026-09-16")
    assert items[0]["kind"] == "press_monetary"

def test_fetch_returns_empty_on_http_failure(monkeypatch):
    import requests as _req
    from apps.market.services import fed
    monkeypatch.setattr(fed.requests, "get", lambda *a, **k: (_ for _ in ()).throw(_req.ConnectionError()))
    assert fed.fetch_fed_communications() == []

def test_dtd_and_entity_declarations_rejected():
    import pytest
    from apps.market.services.fed import _parse
    evil = b"<?xml version='1.0'?><!DOCTYPE r [<!ENTITY a 'x'>]><rss><channel/></rss>"
    with pytest.raises(ValueError, match="DTD/entity"):
        _parse("speeches", evil)

def test_size_cap_rejects_oversized_feed(monkeypatch):
    from apps.market.services import fed
    class _Resp:
        raw = type("R", (), {"read": staticmethod(lambda n, decode_content=True: b"x" * n)})()
        def raise_for_status(self): pass
    monkeypatch.setattr(fed.requests, "get", lambda *a, **k: _Resp())
    assert fed.fetch_fed_communications() == []      # oversized → [] (never raises)
```

(Bypass the Redis cache in tests the way other market-service tests do — patch `fed.cache.get_or_fetch` to call the fetcher directly, or use the repo's existing cache-stub fixture.)

- [ ] **Step 3: Run to verify failure** — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `fed.py`**

```python
"""Federal Reserve communications via the Fed's public RSS feeds. Keyless.

Follows the treasury.py/edgar.py contract: requests + descriptive User-Agent,
Redis-cached, returns [] on ANY failure (a quiet feed or a Fed outage must
never fail a snapshot section)."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

from apps.market import cache
from apps.market.services.safe_log import safe_err

log = logging.getLogger(__name__)

FEEDS = {
    # Confirmed at implementation time (Step 1).
    "press_monetary": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "speeches": "https://www.federalreserve.gov/feeds/speeches.xml",
    "testimony": "https://www.federalreserve.gov/feeds/testimony.xml",
}
_MAX_BYTES = 512 * 1024
_UA = "Ledger single-user market dashboard (github.com/dan-wiseman94/ledger)"

_MOCK_ITEMS = [
    {"kind": "press_monetary", "title": "Federal Reserve issues FOMC statement",
     "url": "https://www.federalreserve.gov/newsevents/pressreleases/mock.htm",
     "published": "2026-09-16T18:00:00+00:00", "summary": "Mock FOMC statement."},
    {"kind": "speeches", "title": "Chair speech: The economic outlook",
     "url": "https://www.federalreserve.gov/newsevents/speech/mock.htm",
     "published": "2026-09-15T14:00:00+00:00", "summary": "Mock speech."},
]


def fetch_fed_communications(*, limit: int = 10) -> list[dict]:
    """Newest-first items across all feeds; [] on any failure."""
    if _is_mock():
        return list(_MOCK_ITEMS)
    items: list[dict] = []
    for kind, url in FEEDS.items():
        items.extend(_fetch_feed(kind, url))
    items.sort(key=lambda i: i.get("published") or "", reverse=True)
    return items[:limit]


def _is_mock() -> bool:
    # Import the mock gate from wherever the sibling services do (grep
    # `is_mock_mode` in apps/market/services and mirror that exact import).
    from apps.market.services.polygon import is_mock_mode  # adjust to the real home

    return is_mock_mode()


def _fetch_feed(kind: str, url: str) -> list[dict]:
    def _pull() -> list[dict]:
        resp = requests.get(url, timeout=10, headers={"User-Agent": _UA}, stream=True)
        resp.raise_for_status()
        raw = resp.raw.read(_MAX_BYTES + 1, decode_content=True)
        if len(raw) > _MAX_BYTES:
            raise ValueError("feed exceeds size cap")
        return _parse(kind, raw)

    try:
        return cache.get_or_fetch(
            f"market:fed:{kind}", ttl_seconds=cache.ttl_for_kind("fed"), fetcher=_pull
        )
    except Exception as exc:
        log.warning("market.fed fetch failed for %s: %s", kind, safe_err(exc))
        return []


def _parse(kind: str, raw: bytes) -> list[dict]:
    # The defusedxml attack classes (XXE, billion-laughs) both require DTD or
    # entity declarations — reject them outright, plus the size cap upstream.
    # This is defusedxml's forbid_dtd/forbid_entities behavior without the dep
    # (the worktree test harness reuses baked images and can't add packages).
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise ValueError("DTD/entity declarations rejected")
    root = ET.fromstring(raw)  # noqa: S314  # nosemgrep: <rule-id from `semgrep ci` run> -- DTD/entities rejected above; size-capped
    out: list[dict] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        pub = (item.findtext("pubDate") or "").strip()
        try:
            published = parsedate_to_datetime(pub).isoformat() if pub else None
        except (TypeError, ValueError):
            published = None
        out.append(
            {
                "kind": kind,
                "title": title,
                "url": (item.findtext("link") or "").strip(),
                "published": published,
                "summary": (item.findtext("description") or "").strip()[:300],
            }
        )
    return out
```

  Fix the `_is_mock` import to the real location before committing, add `"fed": 3600` to `cache.py`'s TTL table, and replace the `nosemgrep` placeholder with the actual rule id: run `$DC run --rm --no-deps -T --entrypoint "" -w /app web uvx semgrep --config p/python --config p/security-audit backend/apps/market/services/fed.py` and copy the reported id (the repo convention is an inline `# nosemgrep: <full-id> -- reason`, precedent `market/tasks.py:65`).

- [ ] **Step 5: Run** — `… pytest apps/market/tests/test_fed.py -v` → PASS; `ruff check`.

- [ ] **Step 6: Commit** — `feat(market): keyless Fed communications service (RSS)`

---

### Task 13: `flowlite` service — volume-based flow proxy (spec 6.2)

**Files:**
- Create: `backend/apps/snapshots/services/flowlite.py`
- Modify: `backend/apps/market/services/option_analytics.py` (public `flatten_expiries` + `put_call_from_expiries` helpers)
- Test: `backend/apps/snapshots/tests/test_flowlite.py` (new), `backend/apps/market/tests/test_option_analytics.py`

**Interfaces:**
- Produces (Task 14 consumes): `build_flowlite_payload(*, watchlist_tickers: list[str], primary: str) -> dict` with keys `proxy_note` (fixed string), `volume_z: [{"ticker","z","latest","avg"}]` (|z| descending), `put_call_delta: {"ticker","latest","prior","delta"}|None`, `unusual: list` (≤3 flagged rows).
- Produces: `option_analytics.flatten_expiries(expiries: dict) -> list[dict]` (sides mapped `calls→call`, `puts→put`, expiry stamped) and `put_call_from_expiries(expiries: dict) -> dict` (the `_put_call` ratios).

- [ ] **Step 1: Failing tests** — (a) option_analytics: `flatten_expiries({"2026-10-16": {"calls": [{"strike": 100}], "puts": [{"strike": 95}]}})` yields two rows with `side`/`expiry` stamped; `put_call_from_expiries` returns the `_put_call` dict. (b) flowlite: seed 21 daily `OHLCBar` rows for SPY with flat volume then a 3σ spike → `volume_z[0]["ticker"] == "SPY"` and `z > 2`; two seeded `OptionChainSnapshot` rows for the primary → `put_call_delta["delta"]` equals latest ratio minus prior; empty DB → all keys present, lists empty, `put_call_delta is None`; `proxy_note` always present.

- [ ] **Step 2: Implement the option_analytics helpers** (module bottom):

```python
def flatten_expiries(expiries: dict) -> list[dict]:
    """Flatten a chain payload's {expiry: {calls: [...], puts: [...]}} into the
    per-contract list chain_analytics consumes."""
    flat: list[dict] = []
    for exp, section in (expiries or {}).items():
        for c in section.get("calls", []):
            flat.append({**c, "side": "call", "expiry": exp})
        for p in section.get("puts", []):
            flat.append({**p, "side": "put", "expiry": exp})
    return flat


def put_call_from_expiries(expiries: dict) -> dict:
    return _put_call(flatten_expiries(expiries))
```

- [ ] **Step 3: Implement `flowlite.py`** — read `OptionChainSnapshot`'s field names in `backend/apps/market/models.py` first (the ticker column, the JSON payload column holding the `expiries` dict, and the capture-timestamp column) and use them where marked:

```python
"""Volume-based flow-pressure proxy. NOT fund-flow data — no free per-ETF
flow source exists (spec 6.2); every render of this payload says so."""

from __future__ import annotations

import logging
import statistics

from django.utils import timezone

from apps.market.models import OHLCBar, OptionChainSnapshot

log = logging.getLogger(__name__)

PROXY_NOTE = "volume-based flow proxy — not fund-flow data"
_CORE = ["SPY", "QQQ"]


def build_flowlite_payload(*, watchlist_tickers: list[str], primary: str) -> dict:
    from apps.market.services.context import SECTOR_ETFS

    tickers = _CORE + [s for s in SECTOR_ETFS if s not in _CORE]
    volume_z = sorted(
        (z for t in tickers if (z := _volume_zscore(t)) is not None),
        key=lambda r: abs(r["z"]),
        reverse=True,
    )
    return {
        "proxy_note": PROXY_NOTE,
        "volume_z": volume_z,
        "put_call_delta": _put_call_delta(primary),
        "unusual": _unusual(primary),
    }


def _volume_zscore(ticker: str, *, window: int = 20) -> dict | None:
    vols = [
        float(b.volume or 0)
        for b in OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d").order_by("-ts")[
            : window + 1
        ]
    ]
    if len(vols) < window + 1:
        return None
    latest, hist = vols[0], vols[1:]
    stdev = statistics.pstdev(hist)
    if not stdev:
        return None
    return {
        "ticker": ticker.upper(),
        "z": round((latest - statistics.fmean(hist)) / stdev, 2),
        "latest": int(latest),
        "avg": int(statistics.fmean(hist)),
    }


def _put_call_delta(primary: str) -> dict | None:
    from apps.market.services.option_analytics import put_call_from_expiries

    rows = list(
        OptionChainSnapshot.objects.filter(ticker=primary.upper())  # adjust field names
        .order_by("-captured_at")[:2]                                # to the real model
    )
    if len(rows) < 2:
        return None
    latest = put_call_from_expiries(rows[0].payload.get("expiries") or {}).get("volume_ratio")
    prior = put_call_from_expiries(rows[1].payload.get("expiries") or {}).get("volume_ratio")
    if latest is None or prior is None:
        return None
    return {
        "ticker": primary.upper(),
        "latest": latest,
        "prior": prior,
        "delta": round(latest - prior, 4),
    }


def _unusual(primary: str) -> list:
    try:
        from apps.analytics.services.unusual_options import unusual_options

        return list(unusual_options(ticker=primary.upper(), at=timezone.now(), top_n=3))
    except Exception as exc:
        log.debug("flowlite unusual-options skipped: %s", exc)
        return []
```

- [ ] **Step 4: Run** — both new test modules → PASS. `ruff check` (watch `C901` stays ≤15 everywhere).

- [ ] **Step 5: Commit** — `feat(snapshots): flowlite volume-based flow-proxy service`

---

### Task 14: wire the `fed` + `flowlite` section kinds (spec §6 gate stack)

**Files:**
- Modify: `backend/apps/snapshots/models.py` (`KIND_CHOICES` + migration), `backend/apps/snapshots/services/__init__.py` (`_FETCHERS`), `backend/apps/snapshots/serializer.py` (`_title`, `_RENDERERS`, two renderers), `backend/apps/snapshots/token_budget.py` (`_PRUNE_ORDER`), the token-budget Hypothesis property test, `backend/schema.yml` + `frontend/src/api/schema.d.ts` (regen)
- Test: snapshots section/serializer/token-budget tests

**Interfaces:**
- Consumes: `fetch_fed_communications` (Task 12), `build_flowlite_payload` (Task 13), `_pick_ticker` (existing).

- [ ] **Step 1: Failing tests** — (a) model: `"fed"` and `"flowlite"` are valid `SnapshotSection.kind` choices (both ≤16 chars); (b) prune order: `_PRUNE_ORDER == ["chain", "ohlc", "news", "fed", "flowlite", "breadth", "quotes", "positions"]` and `prune_to_budget` drops `fed` before `breadth`; (c) renders: a fed payload renders `## Fed communication` with a next-FOMC line when a future `MarketEvent(kind="fomc")` exists; a flowlite payload renders the proxy disclaimer in its heading and an `-σ` volume line; empty payloads render honest `_(…)_` fallbacks.

- [ ] **Step 2: Model + migration** — add to `KIND_CHOICES` in `snapshots/models.py` (mirror the existing tuple style): `("fed", "Fed communication")`, `("flowlite", "Flow proxy")`. Then `$DC run --rm --no-deps -T web uv run python manage.py makemigrations snapshots` and run the **migration-reviewer** agent on the result. `makemigrations --check --dry-run` → clean afterwards.

- [ ] **Step 3: Fetchers** — in `_FETCHERS` add (imports at the top of the module beside the existing service imports):

```python
    "fed": lambda **_: {"data": {"items": fetch_fed_communications()}},
    "flowlite": lambda *, watchlist_tickers, ohlc_ticker=None, **_: {
        "data": build_flowlite_payload(
            watchlist_tickers=list(watchlist_tickers),
            primary=_pick_ticker(ohlc_ticker, list(watchlist_tickers)),
        )
    },
```

- [ ] **Step 4: Renderers** — in `serializer.py` add `"fed": "Fed communication"`, `"flowlite": "Flow proxy (volume-based)"` to `_title`, register both in `_RENDERERS`, and implement:

```python
def _render_fed(payload) -> str:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    lines = ["## Fed communication"]
    fomc = _next_fomc_line()
    if fomc:
        lines.append(fomc)
    if not items:
        lines.append("_(no recent Fed communications)_")
        return "\n".join(lines)
    for it in items[:10]:
        when = (it.get("published") or "")[:10] or "?"
        lines.append(f"- **{when}** [{it.get('kind')}] [{it.get('title')}]({it.get('url')})")
    return "\n".join(lines)


def _next_fomc_line() -> str:
    from apps.market.models import MarketEvent

    # Confirm MarketEvent's date + kind field names in apps/market/models.py
    # and mirror the query upcoming_events uses for macro kinds.
    ev = (
        MarketEvent.objects.filter(kind="fomc", date__gte=timezone.now().date())
        .order_by("date")
        .first()
    )
    if ev is None:
        return ""
    days = (ev.date - timezone.now().date()).days
    return f"- Next FOMC decision in {days}d ({ev.date.isoformat()})"


def _render_flowlite(payload) -> str:
    lines = ["## Flow proxy (volume-based — not fund-flow data)"]
    vz = payload.get("volume_z") or [] if isinstance(payload, dict) else []
    if vz:
        lines.append(
            "- Volume z vs 20d avg: " + ", ".join(f"{r['ticker']} {r['z']:+.1f}σ" for r in vz[:8])
        )
    pc = payload.get("put_call_delta") if isinstance(payload, dict) else None
    if isinstance(pc, dict):
        lines.append(
            f"- {pc['ticker']} P/C volume ratio {pc['latest']:.2f} "
            f"(Δ {pc['delta']:+.2f} vs prior chain)"
        )
    unusual = payload.get("unusual") or [] if isinstance(payload, dict) else []
    for row in unusual:
        lines.append(f"- Unusual: {_describe_unusual(row)}")
    if len(lines) == 1:
        lines.append("_(insufficient stored data — needs nightly bar ingest + a prior chain)_")
    return "\n".join(lines)
```

  (`_describe_unusual` exists from Task 7. `timezone` — use the import style already present in `serializer.py`.)

- [ ] **Step 5: Prune order** — `_PRUNE_ORDER = ["chain", "ohlc", "news", "fed", "flowlite", "breadth", "quotes", "positions"]` and update the comment: the two new sections are enrichment — they drop after news, before core context. Update the Hypothesis token-budget property test's kind universe to include the two new kinds.

- [ ] **Step 6: Schema** — `$DC run --rm --no-deps -T -w /app/backend web uv run python manage.py spectacular --file schema.yml --validate`; commit the regenerated `backend/schema.yml`. Regenerate `frontend/src/api/schema.d.ts` via the copied-schema workaround (memory: `gen:api` is broken in-container — copy `schema.yml` into the frontend container and run openapi-typescript against it).

- [ ] **Step 7: Run** — snapshots model + serializer + token-budget (incl. Hypothesis) tests → PASS. `make check-migrations` equivalent via `$DC` → clean.

- [ ] **Step 8: Commit** — `feat(snapshots): fed + flowlite section kinds wired end-to-end`

---

### Task 15: rich DEFAULT_INCLUDES + data migration (spec A1)

**Files:**
- Modify: `backend/apps/profiles/models.py` (`DEFAULT_INCLUDES`)
- Create: `backend/apps/profiles/migrations/00XX_backfill_default_includes.py`
- Test: `backend/apps/profiles/tests/`

- [ ] **Step 1: Failing tests**

```python
NEW_DEFAULTS = ["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"]

def test_new_profile_seeds_rich_defaults(db):
    from apps.profiles.models import TradingProfile
    p = TradingProfile.objects.create(name="t", style="s")
    assert p.default_includes == NEW_DEFAULTS

def test_backfill_appends_missing_and_preserves_custom(db):
    from django.apps import apps as django_apps
    from apps.profiles.migrations import _backfill  # thin module the migration imports
    from apps.profiles.models import TradingProfile
    p = TradingProfile.objects.create(name="t", style="s")
    TradingProfile.objects.filter(pk=p.pk).update(
        default_includes=["quotes", "notes", "chain"]  # user-trimmed + custom order
    )
    _backfill.add_kinds(django_apps, None)
    p.refresh_from_db()
    # Missing kinds append in KINDS order — positions/breadth land before ohlc.
    assert p.default_includes == ["quotes", "notes", "chain", "positions", "breadth",
                                  "ohlc", "news", "events", "macro"]
    _backfill.add_kinds(django_apps, None)             # idempotent
    p.refresh_from_db()
    assert p.default_includes.count("chain") == 1
```

- [ ] **Step 2: Implement** — (a) `DEFAULT_INCLUDES` becomes the eight-kind list above (order matters: existing trio first). (b) Create `backend/apps/profiles/migrations/_backfill.py`:

```python
"""Shared by the backfill migration and its tests. Literal list on purpose —
migrations must not read the live model constant."""

KINDS = ["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"]


def add_kinds(apps, schema_editor) -> None:
    TradingProfile = apps.get_model("profiles", "TradingProfile")
    for p in TradingProfile.objects.all():
        includes = list(p.default_includes or [])
        missing = [k for k in KINDS if k not in includes]
        if missing:
            p.default_includes = includes + missing
            p.save(update_fields=["default_includes"])
```

  and the migration calling `RunPython(add_kinds, migrations.RunPython.noop)`. Run the **migration-reviewer** agent on it.

- [ ] **Step 3: Run** — profiles tests → PASS. Note the cost consequence is documented in Task 17's CLAUDE.md edit (spec §9's corrected numbers), not here.

- [ ] **Step 4: Commit** — `feat(profiles): rich default snapshot includes + backfill migration`

---

### Task 16: frontend include ceilings (spec A2)

**Files:**
- Modify: `frontend/src/pages/profiles/types.ts` (`SECTION_OPTIONS`), the profile form component that renders it, `frontend/src/components/**/SnapshotSectionPicker.tsx`, `frontend/src/pages/SchedulesPage.tsx`, `frontend/src/api/observer.ts` (type only if needed)
- Test: colocated vitest files for each

- [ ] **Step 1: Failing tests** — (a) `SECTION_OPTIONS` covers every backend kind except `vix` (write the parity list literally in the test):

```ts
const ALL_KINDS = ["quotes","ohlc","chain","positions","breadth","news","events","macro",
  "fundamentals","filings","treasury","overnight","image","notes","fed","flowlite"];
expect([...SECTION_OPTIONS]).toEqual(ALL_KINDS);
```

  (b) the profile form shows a non-toggleable "VIX term structure — always included" chip; (c) SchedulesPage renders a section-includes editor and saving PATCHes `default_includes` on the schedule (MSW asserts the body); (d) SnapshotSectionPicker offers `overnight`, `fundamentals`, `fed`, `flowlite`.

- [ ] **Step 2: Implement** — `SECTION_OPTIONS` becomes the 16-kind list above; render labels via a `SECTION_LABELS` map mirroring the backend `_title` strings. SchedulesPage: reuse `SnapshotSectionPicker` (import it; if its props are composer-specific, extract the checkbox list into a shared component both use) bound to the schedule's `default_includes` with empty = "inherit profile" (render that hint). Follow the existing page's mutation + `useQueryClient` invalidation pattern.

- [ ] **Step 3: Run** — `$DC run --rm --no-deps -T frontend pnpm exec vitest run src/pages/profiles src/pages/SchedulesPage.test.tsx` (adjust paths to the repo's colocated layout) → PASS; `pnpm run lint` + `tsc` clean via the frontend lint script.

- [ ] **Step 4: Commit** — `feat(frontend): full section pickers for profiles, composer, and schedules`

---

### Task 17: docs + final gate (spec §11)

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `FEATURES.md`, `docs/marketing-copy.md`

- [ ] **Step 1: CLAUDE.md** — in the capture-pipeline paragraph and the snapshots conventions: add `fed`/`flowlite` to the section list, the new `_PRUNE_ORDER`, the new eight-kind `DEFAULT_INCLUDES` (keeping the seeds-only-empty landmine, now with "backfilled by migration 00XX"), and one new landmine line: **live-quote lines in default sections reduce `OBSERVER_RESPONSE_CACHE_ENABLED` hits (byte-identical prompts become rare), and rich defaults multiply scheduled-fire input tokens — ≈$17–65/day input for a 10-min Opus schedule at ~30k tokens/fire; per-schedule `default_includes` is the lever.**

- [ ] **Step 2: README + FEATURES + marketing-copy** — extend the capability bullets: credit spreads (HY/IG OAS), VVIX line, dollar line, factor returns, sector table, GEX by strike + unusual activity in the chain section, Form 4 insider filings, the `fed` section, the `flowlite` proxy (always labeled a proxy), 52-week stored history + longer-horizon summary. Present-tense capabilities only (no "new"/milestone framing — style memory).

- [ ] **Step 3: Full gate** — backend: `$DC run --rm --no-deps -T web uv run pytest` (whole suite) and ruff/mypy/import-linter via the `-w /app --entrypoint ""` form; frontend: vitest + lint. Then run the `conventions-check` skill over the branch diff. Fix anything red.

- [ ] **Step 4: Commit** — `docs: snapshot macro-desk coverage capabilities`

---

## Deferred: Workstream E (post-TradingView)

The TV symbol-map rows ($VVIX/DXY/curve tenors/SKEW//ZQ), the `yields.py` per-tenor divisor (the spec §7 unit-contract blocker), and the optional TV-direct 2Y consult become a separate small plan once `worktree-tradingview-mcp` merges — its `INDEX_SYMBOLS`/`FUTURE_SYMBOLS` dicts don't exist on this branch. Do not start it from this plan.
