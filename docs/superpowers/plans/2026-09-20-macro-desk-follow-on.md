# Macro-Desk Follow-On (Workstream E + fix-later items) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the TradingView symbol/unit rows that Workstream E was blocked on (yield tenors, VVIX, DXY, SKEW, ZQ, VX2), close the yields unit hazard the spec review called a blocker, and clear the seven non-blocking fix-later items from the follow-on doc's §5.

**Architecture:** Yield-index *units* are normalized at the **provider boundary** (a `_QUOTE_SCALE` table in `apps/market/services/tradingview.py`), not in `yields.py`, because `$TNX` is consumed in three places (`live_yields`, the breadth `MACRO` row, and any watchlist quote) — a divisor that lived only in `yields.py` would leave the other two flipping units by provider. `YIELD_INDICES` still becomes `ticker -> (tenor, divisor)` so each row *states* its unit rather than inheriting a blanket `/10`. A small, deliberate per-symbol provider merge lets `live_yields` reach TradingView directly for the 2Y tenor Schwab has no index for.

**Tech Stack:** Django 5 / DRF, pytest (`-m 'not integration'`), Docker Compose (`web` container, WORKDIR `/app/backend`), ruff + mypy (zero baseline) + import-linter + semgrep.

**Spec:** `docs/superpowers/specs/2026-09-19-macro-desk-follow-on-work.md` (§1 Workstream E, §5 execution learnings)

## Global Constraints

- All commands run in Docker. One backend test: `docker compose exec -T web pytest apps/<app>/tests/test_<x>.py::<name> -v` (drop the `backend/` prefix — container WORKDIR is `/app/backend`).
- Lint from `/app`: `docker compose exec -T -w /app web ruff check backend` and `... ruff format --check backend`.
- **TradingView is NOT connected in this environment** (`load_token()` is None). No symbol row in this plan can be live-verified here. Every new row must therefore degrade to "no row" rather than to a wrong number: an unmappable TradingView symbol already yields no quote, `_usable()` filters non-positive `last`, and `live_yields` skips a tenor with no usable quote. Live verification stays a user action (see Task 9).
- **TradingView is a paid-plan OAuth source.** Never list it under "free data sources" in any doc.
- App-wide unit contract (load-bearing, state it in code comments): **every `$`-prefixed Treasury-yield ticker quotes yield x 10** (the Schwab/CBOE convention `apps/market/symbols.py` already documents). A provider that publishes percent is scaled at its own boundary.
- `Notification.kind` is `varchar(16)`; `SnapshotSection.KIND_CHOICES` is `max_length=16`. Nothing in this plan adds either, but do not widen them.
- Conventional, bite-sized commits: `feat(market):`, `fix(snapshots):`, `refactor(market):`, `docs:`. Use `LEFTHOOK=0 git commit` when `e2e/*.py` is staged (not expected here).

---

## File Structure

| File | Responsibility in this plan |
|---|---|
| `backend/apps/market/services/yields.py` | `YIELD_INDICES` becomes `ticker -> (tenor, divisor)`; adds the `$US2Y` tenor and the TradingView-direct merge for Schwab-less tenors |
| `backend/apps/market/services/tradingview.py` | New `INDEX_SYMBOLS` / `FUTURE_SYMBOLS` rows; new `_QUOTE_SCALE` boundary unit table applied in `fetch_quotes` |
| `backend/apps/market/symbols.py` | `DXY` / `SKEW` / `VVIX` index aliases; `ZQ` added to `CME_FUTURE_ROOTS` |
| `backend/apps/market/services/vix.py` | `/VX2` continuous second-month fallback |
| `backend/apps/market/services/intel.py` | `factor_returns` reuses its own computed legs instead of re-querying |
| `backend/apps/market/services/events.py`, `backend/apps/snapshots/services/__init__.py` | Shared `EVENTS_WINDOW_DAYS` constant replaces the duplicated `14` |
| `backend/apps/market/services/fed.py` | Streamed response closed via `with` |
| `backend/apps/profiles/migrations/0013_backfill_default_includes.py` | One-line comment explaining the noop reverse |
| `backend/apps/snapshots/serializer.py` | Live 2s10s line; continuous-second VIX label; treasury `record_date` provenance; dead `_RENDERERS["ohlc"]` entry removed |
| `README.md`, `CLAUDE.md`, `FEATURES.md`, the follow-on spec | Doc touchpoints |

---

### Task 1: Yields unit contract — `ticker -> (tenor, divisor)`

`yields.py` today divides *every* quote by 10. That is correct only for CBOE `$`-yield
indices. Making the divisor per-row is what stops a future percent-quoting source from
silently rendering 10x low while still passing the `last > 0` gate.

**Files:**
- Modify: `backend/apps/market/services/yields.py:19-40`
- Test: `backend/apps/market/tests/test_yields.py`

**Interfaces:**
- Consumes: `apps.market.services.quotes.fetch_quotes(list[str]) -> dict[str, dict]`
- Produces: `YIELD_INDICES: dict[str, tuple[str, float]]` mapping app ticker -> `(tenor, divisor)`.
  `live_yields() -> dict` keeps its existing shape `{tenor: {"ticker": str, "yield_pct": float}}`.

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/market/tests/test_yields.py`:

```python
def test_live_yields_honors_a_per_row_divisor():
    """A row whose source publishes percent must not be divided by 10.

    The unit lives on the row, not in the function — this is the guard that
    stopped a percent-quoting tenor rendering 10x low.
    """
    table = {"$TNX": ("10Y", 10.0), "$PCT": ("2Y", 1.0)}
    with (
        patch.object(yields_mod, "YIELD_INDICES", table),
        patch.object(
            yields_mod,
            "fetch_quotes",
            return_value={"$TNX": {"last": 47.1}, "$PCT": {"last": 4.15}},
        ),
    ):
        out = yields_mod.live_yields()
    assert out["10Y"]["yield_pct"] == 4.71
    assert out["2Y"]["yield_pct"] == 4.15
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose exec -T web pytest apps/market/tests/test_yields.py::test_live_yields_honors_a_per_row_divisor -v`

Expected: FAIL — `ValueError: too many values to unpack` or `out["2Y"]["yield_pct"] == 0.415`
(the current loop unpacks `ticker, tenor` and divides by a hardcoded 10).

- [ ] **Step 3: Rewrite the map and the loop**

Replace `backend/apps/market/services/yields.py` lines 19-40 with:

```python
# App ticker -> (tenor, divisor). The divisor is the row's own unit, not a
# global: CBOE $-yield indices quote yield x 10 ($TNX 47.1 == 4.71%), and the
# app normalizes every $-prefixed yield ticker to that convention at the
# provider boundary (apps.market.services.tradingview._QUOTE_SCALE), so a
# fallback provider that publishes percent cannot land here unscaled. A source
# that ever does gets divisor 1.0 on its own row instead of a silent 10x error.
YIELD_INDICES: dict[str, tuple[str, float]] = {
    "$IRX": ("13W", 10.0),
    "$FVX": ("5Y", 10.0),
    "$TNX": ("10Y", 10.0),
    "$TYX": ("30Y", 10.0),
}


def live_yields() -> dict:
    """{tenor: {"ticker", "yield_pct"}} for whichever yield indices quote."""
    try:
        quotes = fetch_quotes(list(YIELD_INDICES))
    except Exception as exc:
        log.warning("market.yields.quotes_unavailable: %s", safe_err(exc))
        return {}
    out: dict = {}
    for ticker, (tenor, divisor) in YIELD_INDICES.items():
        last = (quotes.get(ticker) or {}).get("last")
        if isinstance(last, int | float) and last > 0:
            out[tenor] = {"ticker": ticker, "yield_pct": round(last / divisor, 3)}
    return out
```

Also update the module docstring's last sentence to read:

```
so dividing by that row's divisor recovers percent. Best-effort: {} whenever
index quotes are unavailable (e.g. a fallback provider that carries no index
quotes).
```

- [ ] **Step 4: Run the full yields test file**

Run: `docker compose exec -T web pytest apps/market/tests/test_yields.py -v`

Expected: PASS (4 tests — the 3 existing ones are unit-agnostic and still hold).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/yields.py backend/apps/market/tests/test_yields.py
git commit -m "refactor(market): yield rows carry their own unit divisor"
```

---

### Task 2: TradingView yield/vol/dollar symbol rows + boundary unit scale

TradingView's `US02Y/US03MY/US05Y/US10Y/US30Y` publish yield **in percent**, while the app's
`$`-prefixed yield tickers are defined as yield x 10. Scaling at the provider boundary keeps
that one contract true for *every* consumer (`live_yields`, the breadth `MACRO` row, a
watchlist quote), not just for `yields.py`.

`$TNX` moves from `TVC:TNX` to `TVC:US10Y` on purpose: `TVC:TNX`'s units cannot be verified
in this environment, and the `USxxY` family gives one convention and one scale rule across
all five tenors.

**Files:**
- Modify: `backend/apps/market/services/tradingview.py:33-68` (symbol tables + new `_QUOTE_SCALE`), `:251-279` (`fetch_quotes`)
- Test: `backend/apps/market/tests/test_tradingview_provider.py`

**Interfaces:**
- Consumes: `to_tv_symbol(ticker) -> str | None`, `_batch_rows(result) -> dict[str, dict]`
- Produces: `_QUOTE_SCALE: dict[str, float]` (TradingView symbol -> multiplier applied to
  `last`/`high`/`low`). New `INDEX_SYMBOLS` keys `$VVIX`, `$DXY`, `$SKEW`, `$IRX`, `$FVX`,
  `$TYX`, `$US2Y`; new `FUTURE_SYMBOLS` keys `/ZQ`, `/VX2`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/market/tests/test_tradingview_provider.py`:

```python
@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("$VVIX", "TVC:VVIX"),
        ("$DXY", "TVC:DXY"),
        ("$SKEW", "CBOE:SKEW"),
        ("$IRX", "TVC:US03MY"),
        ("$FVX", "TVC:US05Y"),
        ("$TNX", "TVC:US10Y"),
        ("$TYX", "TVC:US30Y"),
        ("$US2Y", "TVC:US02Y"),
        ("/ZQ", "CBOT:ZQ1!"),
        ("/VX2", "CFE:VX2!"),
    ],
)
def test_macro_desk_symbol_rows(ticker, expected):
    assert tv.to_tv_symbol(ticker) == expected


@pytest.mark.django_db
def test_yield_quotes_are_scaled_to_the_app_times_ten_convention():
    """TradingView publishes US##Y in percent; the app's $-yield tickers are x10.

    Scaling here (not in yields.py) is what keeps $TNX the same unit for the
    breadth MACRO row and a watchlist quote, not just for live_yields.
    """
    batch = {
        "data": [
            {"symbol": "TVC:US10Y", "close": 4.71, "high": 4.75, "low": 4.68, "change": 0.4},
            {"symbol": "NASDAQ:AAPL", "close": 190.0, "high": 191.0, "low": 189.0, "change": 0.5},
        ]
    }
    with _tools({"get_symbol_data_batch": batch, "search_symbols": {"symbols": [
        {"symbol": "NASDAQ:AAPL", "ticker": "AAPL", "exchange": "NASDAQ"}
    ]}}):
        out = tv.fetch_quotes(["$TNX", "AAPL"])
    assert out["$TNX"]["last"] == 47.1
    assert out["$TNX"]["high"] == 47.5
    assert out["$TNX"]["low"] == 46.8
    # pct_change is a ratio, never scaled.
    assert out["$TNX"]["pct_change"] == 0.4
    # An unscaled symbol passes through untouched.
    assert out["AAPL"]["last"] == 190.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec -T web pytest apps/market/tests/test_tradingview_provider.py -k "macro_desk_symbol_rows or times_ten" -v`

Expected: FAIL — `to_tv_symbol("$VVIX")` returns `None`, `to_tv_symbol("$TNX")` returns
`"TVC:TNX"`, and `out["$TNX"]["last"] == 4.71`.

- [ ] **Step 3: Add the symbol rows and the scale table**

In `backend/apps/market/services/tradingview.py`, replace the `INDEX_SYMBOLS` /
`FUTURE_SYMBOLS` block (lines 33-63) with:

```python
# App spelling -> TradingView symbol. None = no TradingView equivalent (breadth internals).
INDEX_SYMBOLS: dict[str, str | None] = {
    "$VIX": "TVC:VIX",
    "$VVIX": "TVC:VVIX",
    "$SKEW": "CBOE:SKEW",
    "$DXY": "TVC:DXY",
    "$SPX": "SP:SPX",
    "$NDX": "NASDAQ:NDX",
    "$DJI": "DJ:DJI",
    "$RUT": "TVC:RUT",
    # Treasury tenors ride the TVC:US##Y family, which publishes in PERCENT.
    # _QUOTE_SCALE below restores the app's x10 convention at this boundary.
    # $US2Y has no Schwab/CBOE index — it is TradingView-only (see yields.py).
    "$IRX": "TVC:US03MY",
    "$FVX": "TVC:US05Y",
    "$TNX": "TVC:US10Y",
    "$TYX": "TVC:US30Y",
    "$US2Y": "TVC:US02Y",
    "$COMPX": "NASDAQ:IXIC",
    "$OEX": "SP:OEX",
    "$ADVN": None,
    "$DECN": None,
    "$TICK": None,
    "$TRIN": None,
}
FUTURE_SYMBOLS: dict[str, str] = {
    "/ES": "CME_MINI:ES1!",
    "/NQ": "CME_MINI:NQ1!",
    "/RTY": "CME_MINI:RTY1!",
    "/YM": "CBOT_MINI:YM1!",
    "/CL": "NYMEX:CL1!",
    "/GC": "COMEX:GC1!",
    "/SI": "COMEX:SI1!",
    "/ZB": "CBOT:ZB1!",
    "/ZN": "CBOT:ZN1!",
    "/ZF": "CBOT:ZF1!",
    "/NG": "NYMEX:NG1!",
    "/HG": "COMEX:HG1!",
    "/VX": "CFE:VX1!",
    "/VX2": "CFE:VX2!",
    "/ZQ": "CBOT:ZQ1!",
    "/6E": "CME:6E1!",
}
# TradingView symbol -> multiplier that restores the APP's unit for that ticker.
# The app's $-prefixed Treasury-yield tickers follow the Schwab/CBOE convention
# (yield x 10: $TNX 47.1 == 4.71%); TVC:US##Y publishes percent. Normalizing here
# rather than in yields.py keeps one unit across every consumer of $TNX — the
# macro render, the breadth MACRO row, and a plain watchlist quote.
_QUOTE_SCALE: dict[str, float] = {
    "TVC:US03MY": 10.0,
    "TVC:US02Y": 10.0,
    "TVC:US05Y": 10.0,
    "TVC:US10Y": 10.0,
    "TVC:US30Y": 10.0,
}
```

- [ ] **Step 4: Apply the scale in `fetch_quotes`**

In the same file, replace the row-building block inside `fetch_quotes` (the
`out[ticker] = {...}` assignment) with:

```python
        for ticker, symbol in mapping.items():
            row = by_symbol.get(symbol or "")
            if row is None:
                continue
            scale = _QUOTE_SCALE.get(symbol or "", 1.0)
            out[ticker] = {
                "last": _scaled(row.get("close"), scale),
                "bid": None,
                "ask": None,
                "volume": _int(row.get("volume")),
                "high": _scaled(row.get("high"), scale),
                "low": _scaled(row.get("low"), scale),
                # A percent change is a ratio — never scaled.
                "pct_change": _float(row.get("change")),
            }
```

And add this helper immediately after `_float` (near line 110):

```python
def _scaled(value: Any, scale: float) -> float | None:
    v = _float(value)
    return v if v is None or scale == 1.0 else round(v * scale, 6)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose exec -T web pytest apps/market/tests/test_tradingview_provider.py -v`

Expected: PASS (all, including the pre-existing `$VIX`/`SPX` mapping parametrize).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/market/services/tradingview.py backend/apps/market/tests/test_tradingview_provider.py
git commit -m "feat(market): TradingView yield/vol/dollar symbol rows with boundary unit scaling"
```

---

### Task 3: Bare-alias and futures-root coverage for the new symbols

A symbol row is only reachable if `normalize_symbol` can get there. `VIX`/`SPX` already have
aliases; `DXY`/`SKEW`/`VVIX` do not, so a user typing them into a watchlist would hit an
equity lookup. `ZQ` needs to be a known futures root so both the fetch boundary and
`calendar.heuristics` classify it as a CME future.

**Files:**
- Modify: `backend/apps/market/symbols.py:24-42`
- Test: `backend/apps/market/tests/test_symbols.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `normalize_symbol("DXY") == "$DXY"`, `normalize_symbol("SKEW") == "$SKEW"`,
  `normalize_symbol("VVIX") == "$VVIX"`, `normalize_symbol("ZQ") == "/ZQ"`;
  `classify("ZQ") == "cme_futures"`.

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/market/tests/test_symbols.py`:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("dxy", "$DXY"),
        ("SKEW", "$SKEW"),
        ("vvix", "$VVIX"),
        ("zq", "/ZQ"),
    ],
)
def test_macro_desk_aliases(raw, expected):
    assert normalize_symbol(raw) == expected


def test_zq_classifies_as_a_cme_future():
    """The fetch boundary and the calendar must agree — both read symbols.py."""
    from apps.market.calendar.heuristics import classify

    assert classify("ZQ") == "cme_futures"
    assert classify("/ZQ") == "cme_futures"


def test_new_index_aliases_are_not_equity_like():
    for alias in ("DXY", "SKEW", "VVIX"):
        assert is_equity_like(alias) is False
```

If `test_symbols.py` does not already import `pytest`, `normalize_symbol`, and
`is_equity_like`, add them at the top:

```python
import pytest

from apps.market.symbols import is_equity_like, normalize_symbol
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose exec -T web pytest apps/market/tests/test_symbols.py -k "macro_desk or zq_classifies or new_index_aliases" -v`

Expected: FAIL — `normalize_symbol("dxy")` returns `"DXY"`, `classify("ZQ")` returns `"us_equity"`.

- [ ] **Step 3: Add the aliases and the root**

In `backend/apps/market/symbols.py`, extend `INDEX_ALIASES`:

```python
INDEX_ALIASES: dict[str, str] = {
    "SPX": "$SPX",  # S&P 500 index
    "VIX": "$VIX",  # CBOE Volatility Index
    "VVIX": "$VVIX",  # CBOE VIX-of-VIX (vol of vol)
    "SKEW": "$SKEW",  # CBOE SKEW index (tail-risk pricing)
    "DXY": "$DXY",  # US Dollar Index
    "NDX": "$NDX",  # Nasdaq-100 index
    "RUT": "$RUT",  # Russell 2000 index
    "DJI": "$DJI",  # Dow Jones Industrial Average
    "COMPX": "$COMPX",  # Nasdaq Composite index
    "OEX": "$OEX",  # S&P 100 index
}
```

and extend `CME_FUTURE_ROOTS` with `"ZQ"`:

```python
CME_FUTURE_ROOTS: frozenset[str] = frozenset(
    {"ES", "NQ", "RTY", "YM", "CL", "GC", "SI", "ZB", "ZN", "ZF", "NG", "HG", "ZQ"}
)
```

- [ ] **Step 4: Run the symbols + calendar tests**

Run: `docker compose exec -T web pytest apps/market/tests/test_symbols.py apps/market/tests/test_calendar_trading_days.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/symbols.py backend/apps/market/tests/test_symbols.py
git commit -m "feat(market): bare aliases for DXY/SKEW/VVIX and the ZQ futures root"
```

---

### Task 4: `$US2Y` tenor + the deliberate per-symbol TradingView merge

The fallback chain only engages on `SchwabNotConnectedError`, and the locked rule is "the
first configured provider answers, even if it answers empty". Schwab has no 2Y yield index,
so on a Schwab-connected install the 2Y slot would never render no matter how good the
TradingView row is. This is the one deliberate per-symbol provider merge.

**Files:**
- Modify: `backend/apps/market/services/yields.py`
- Test: `backend/apps/market/tests/test_yields.py`

**Interfaces:**
- Consumes: `apps.market.services.tradingview.is_connected() -> bool`,
  `apps.market.services.tradingview.fetch_quotes(list[str]) -> dict[str, dict]`
  (already unit-scaled by Task 2).
- Produces: `YIELD_INDICES` gains `"$US2Y": ("2Y", 10.0)`;
  `TV_ONLY_TENORS: frozenset[str]` naming the tickers Schwab cannot answer.

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/market/tests/test_yields.py`:

```python
def test_two_year_tenor_falls_back_to_tradingview_when_schwab_blanks_it():
    """Schwab has no 2Y yield index, and the fallback chain only engages on
    SchwabNotConnectedError — so a Schwab-connected install needs this merge."""
    with (
        patch.object(
            yields_mod, "fetch_quotes", return_value={"$TNX": {"last": 47.1}}
        ),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch(
            "apps.market.services.tradingview.fetch_quotes",
            return_value={"$US2Y": {"last": 41.5}},
        ),
    ):
        out = yields_mod.live_yields()
    assert out["2Y"] == {"ticker": "$US2Y", "yield_pct": 4.15}
    assert out["10Y"]["yield_pct"] == 4.71


def test_tradingview_merge_is_skipped_when_not_connected():
    with (
        patch.object(yields_mod, "fetch_quotes", return_value={"$TNX": {"last": 47.1}}),
        patch("apps.market.services.tradingview.is_connected", return_value=False) as conn,
        patch("apps.market.services.tradingview.fetch_quotes") as tv_quotes,
    ):
        out = yields_mod.live_yields()
    assert "2Y" not in out
    assert conn.called
    assert not tv_quotes.called


def test_tradingview_merge_never_raises():
    with (
        patch.object(yields_mod, "fetch_quotes", return_value={"$TNX": {"last": 47.1}}),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch(
            "apps.market.services.tradingview.fetch_quotes",
            side_effect=RuntimeError("mcp down"),
        ),
    ):
        out = yields_mod.live_yields()
    assert out["10Y"]["yield_pct"] == 4.71
    assert "2Y" not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec -T web pytest apps/market/tests/test_yields.py -k "two_year or tradingview_merge" -v`

Expected: FAIL — `KeyError: '2Y'` (no `$US2Y` row and no merge).

- [ ] **Step 3: Add the tenor and the merge**

In `backend/apps/market/services/yields.py`, add `"$US2Y": ("2Y", 10.0)` to `YIELD_INDICES`
(between `$IRX` and `$FVX` so the map reads short-to-long), then add below the map:

```python
# Tenors no Schwab index covers. The fallback chain only engages on
# SchwabNotConnectedError, so on a Schwab-CONNECTED install these would never
# resolve — _merge_tv_only asks TradingView for them directly. This is the one
# deliberate per-symbol provider merge; everything else goes through fallback.py.
TV_ONLY_TENORS: frozenset[str] = frozenset({"$US2Y"})
```

and refactor `live_yields` to:

```python
def live_yields() -> dict:
    """{tenor: {"ticker", "yield_pct"}} for whichever yield indices quote."""
    try:
        quotes = fetch_quotes(list(YIELD_INDICES))
    except Exception as exc:
        log.warning("market.yields.quotes_unavailable: %s", safe_err(exc))
        quotes = {}
    quotes = _merge_tv_only(quotes)
    out: dict = {}
    for ticker, (tenor, divisor) in YIELD_INDICES.items():
        last = (quotes.get(ticker) or {}).get("last")
        if isinstance(last, int | float) and last > 0:
            out[tenor] = {"ticker": ticker, "yield_pct": round(last / divisor, 3)}
    return out


def _merge_tv_only(quotes: dict) -> dict:
    """Fill TV_ONLY_TENORS from TradingView directly. Best-effort: any failure
    leaves *quotes* untouched, so the tenor is simply absent (never wrong)."""
    missing = [
        t
        for t in TV_ONLY_TENORS
        if not isinstance((quotes.get(t) or {}).get("last"), int | float)
    ]
    if not missing:
        return quotes
    try:
        from apps.market.services import tradingview

        if not tradingview.is_connected():
            return quotes
        extra = tradingview.fetch_quotes(missing) or {}
    except Exception as exc:
        log.warning("market.yields.tv_merge_failed: %s", safe_err(exc))
        return quotes
    return {**quotes, **{k: v for k, v in extra.items() if v}}
```

Note the `except` around the primary `fetch_quotes` now sets `quotes = {}` and falls through
rather than returning early — a Schwab outage must not also suppress the TradingView tenor.

- [ ] **Step 4: Run the full yields file**

Run: `docker compose exec -T web pytest apps/market/tests/test_yields.py -v`

Expected: PASS (7 tests). `test_live_yields_degrades_to_empty_on_error` still passes: with
TradingView unconnected in tests the merge is a no-op and the result is `{}`.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/yields.py backend/apps/market/tests/test_yields.py
git commit -m "feat(market): live 2Y tenor via a direct TradingView merge"
```

---

### Task 5: Live 2s10s line in the macro render

`_render_macro` currently emits a "30Y - 13W" proxy and defers the real 2s10s to the lagged
FRED row. With a live 2Y the real spread is computable at capture time — that is the whole
point of the tenor.

**Files:**
- Modify: `backend/apps/snapshots/serializer.py:965-981`
- Test: `backend/apps/snapshots/tests/test_serializer_macro.py`

**Interfaces:**
- Consumes: the `live_yields` payload shape `{tenor: {"ticker", "yield_pct"}}` from Task 4.
- Produces: no new callables.

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/snapshots/tests/test_serializer_macro.py`:

```python
def test_macro_renders_a_live_2s10s_when_both_tenors_quote():
    out = _render_macro(
        {
            "series": {},
            "live_yields": {
                "2Y": {"ticker": "$US2Y", "yield_pct": 4.15},
                "10Y": {"ticker": "$TNX", "yield_pct": 4.71},
            },
        }
    )
    assert "| 2Y | 4.15 |" in out
    assert "Live 2s10s: +0.56pp" in out


def test_macro_omits_the_live_2s10s_when_the_2y_is_missing():
    out = _render_macro(
        {"series": {}, "live_yields": {"10Y": {"ticker": "$TNX", "yield_pct": 4.71}}}
    )
    assert "Live 2s10s" not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec -T web pytest apps/snapshots/tests/test_serializer_macro.py -k "2s10s" -v`

Expected: FAIL — `assert "Live 2s10s: +0.56pp" in out`.

- [ ] **Step 3: Add the line**

In `backend/apps/snapshots/serializer.py`, replace the live-curve block inside `_render_macro`
(the `# Live curve proxy (30Y - 13W) spread` comment through the end of that `if live:` body) with:

```python
        # A live 2s10s is the real curve read; the 30Y-13W proxy stays as the
        # wide-curve fallback for captures where the 2Y tenor didn't quote.
        two_y = (live.get("2Y") or {}).get("yield_pct")
        ten_y = (live.get("10Y") or {}).get("yield_pct")
        if isinstance(two_y, int | float) and isinstance(ten_y, int | float):
            lines.append(f"- Live 2s10s: {ten_y - two_y:+.2f}pp (10Y − 2Y at capture time)")
        long_y = (live.get("30Y") or {}).get("yield_pct")
        short_y = (live.get("13W") or {}).get("yield_pct")
        if isinstance(long_y, int | float) and isinstance(short_y, int | float):
            lines.append(f"- Live curve proxy (30Y − 13W): {long_y - short_y:+.2f}pp")
```

This also drops the now-redundant `ly = payload.get("live_yields") or {}` re-read (`live` is
already that dict) and the "official 2s10s is the lagged FRED row" aside, which is no longer
true when the live 2Y quotes.

- [ ] **Step 4: Run the macro serializer tests**

Run: `docker compose exec -T web pytest apps/snapshots/tests/test_serializer_macro.py -v`

Expected: PASS. If an existing test asserts the old "official 2s10s is the lagged FRED"
wording, update that assertion to the new proxy line text.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_macro.py
git commit -m "feat(snapshots): render a live 2s10s from the capture-time yield tenors"
```

---

### Task 6: `/VX2` continuous second-month fallback

Without Schwab, dated `/VXU26`-style legs map to `None`, so the contango read dies even
though TradingView carries a continuous second month. `/VX` already backs the front leg the
same way; this gives the second leg the same safety net.

**Files:**
- Modify: `backend/apps/market/services/vix.py:98-177`
- Modify: `backend/apps/snapshots/serializer.py:1021-1026` (continuous second label)
- Test: `backend/apps/market/tests/test_vix.py`, `backend/apps/snapshots/tests/test_serializer_vix.py`

**Interfaces:**
- Consumes: `FUTURE_SYMBOLS["/VX2"]` from Task 2.
- Produces: `vix_term_structure()` payload's `second` dict gains a `"continuous": bool` key
  (mirroring `front`); `expiry` is `None` when continuous.

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/market/tests/test_vix.py`:

```python
def test_second_leg_falls_back_to_the_continuous_vx2():
    """Free/TradingView fallbacks can't quote a dated /VXU26, but TradingView
    does carry CFE:VX2! — without this the contango read dies off-Schwab."""
    import datetime as dt

    from apps.market.services import vix as vix_mod

    today = dt.date(2026, 9, 20)
    (front_sym, _), (second_sym, _) = vix_mod.front_and_second(today)
    quotes = {
        "$VIX": {"last": 17.0, "pct_change": 1.0},
        "/VX": {"last": 18.0, "pct_change": 0.5},
        "/VX2": {"last": 19.0, "pct_change": 0.4},
    }
    assert front_sym not in quotes and second_sym not in quotes
    with patch.object(vix_mod, "fetch_quotes", return_value=quotes):
        out = vix_mod.vix_term_structure(today=today)
    assert out["second"]["symbol"] == "/VX2"
    assert out["second"]["continuous"] is True
    assert out["second"]["expiry"] is None
    assert out["structure"] == "contango"
    assert out["contango_pct"] == 5.56
```

And append to `backend/apps/snapshots/tests/test_serializer_vix.py`:

```python
def test_vix_render_labels_a_continuous_second_leg():
    from apps.snapshots.serializer import _render_vix

    md = _render_vix(
        {
            "spot": {"symbol": "$VIX", "last": 17.0},
            "second": {"symbol": "/VX2", "expiry": None, "last": 19.0, "continuous": True},
        }
    )
    assert "- Second /VX2 (continuous): 19.00" in md
    assert "exp None" not in md
```

If `test_vix.py` does not already import `patch`, add `from unittest.mock import patch`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec -T web pytest apps/market/tests/test_vix.py -k continuous_vx2 apps/snapshots/tests/test_serializer_vix.py -k continuous_second -v`

Expected: FAIL — `out["second"]` is `None`; the render prints `(exp None)`.

- [ ] **Step 3: Wire the fallback**

In `backend/apps/market/services/vix.py`, inside `vix_term_structure`:

Change the batch call to include `/VX2`:

```python
    quotes = fetch_quotes(["$VIX", "$VVIX", "/VX", "/VX2", front_sym, second_sym])
```

Replace the `second_q = _usable(quotes.get(second_sym))` line with:

```python
    second_q, second_continuous = _usable(quotes.get(second_sym)), False
    if second_q is None and (cont2 := _usable(quotes.get("/VX2"))) is not None:
        second_sym, second_exp, second_q, second_continuous = "/VX2", None, cont2, True
```

and replace the `"second"` entry of the payload dict with:

```python
        "second": (
            {**_leg(second_sym, second_q, second_exp), "continuous": second_continuous}
            if second_q is not None
            else None
        ),
```

Update the function docstring's second paragraph to:

```
    One batched quote call; the continuous ``/VX`` and ``/VX2`` ride along as a
    safety net so a mis-rolled (or un-quotable) dated symbol degrades to a
    continuous leg with no expiry rather than no futures at all.
```

- [ ] **Step 4: Label the continuous second leg in the render**

In `backend/apps/snapshots/serializer.py`, replace the `second` block inside `_render_vix`
(lines 1021-1026) with:

```python
    second = payload.get("second")
    if isinstance(second, dict):
        label = "(continuous)" if second.get("continuous") else f"(exp {second.get('expiry')})"
        lines.append(
            f"- Second {second.get('symbol')} {label}: "
            f"{_fmt(second.get('last'))}{_signed_pct(second.get('pct_change'))}"
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose exec -T web pytest apps/market/tests/test_vix.py apps/snapshots/tests/test_serializer_vix.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/market/services/vix.py backend/apps/snapshots/serializer.py backend/apps/market/tests/test_vix.py backend/apps/snapshots/tests/test_serializer_vix.py
git commit -m "feat(market): continuous /VX2 second-month fallback for the contango read"
```

---

### Task 7: §5 backend hygiene — factor legs, events window, fed response, migration comment

Four independent fix-later items from the follow-on doc's §5. Grouped because each is a
few lines and none carries its own review risk.

**Files:**
- Modify: `backend/apps/market/services/intel.py:98-119`
- Modify: `backend/apps/market/services/events.py:267`, `backend/apps/snapshots/services/__init__.py:167-188`
- Modify: `backend/apps/market/services/fed.py:65-72`
- Modify: `backend/apps/profiles/migrations/0013_backfill_default_includes.py`
- Test: `backend/apps/market/tests/test_intel.py`

**Interfaces:**
- Produces: `apps.market.services.events.EVENTS_WINDOW_DAYS: int = 14`, imported by the
  snapshots events fetcher. `factor_returns` keeps its exact signature and return shape.

- [ ] **Step 1: Write the failing test for the factor-leg reuse**

Append to `backend/apps/market/tests/test_intel.py`, inside the class that holds
`test_factor_returns_shape_and_spreads`:

```python
    def test_factor_returns_reuses_computed_legs(self):
        """Spread legs that are already in `etfs` must not be re-queried —
        the old shape issued ~18 extra indexed queries per context fetch."""
        _factor_returns_bars()
        with patch(
            "apps.market.services.intel.return_over_sessions",
            wraps=intel_mod.return_over_sessions,
        ) as spy:
            out = factor_returns(["MTUM", "VLUE", "QUAL", "USMV", "IWM", "SPY"])
        # 6 ETFs x 3 windows; every spread leg (MTUM/VLUE/IWM/SPY/QQQ) except
        # QQQ is already among them, so only QQQ's 3 windows are extra.
        assert spy.call_count == 6 * 3 + 3
        assert out["spreads"]["momentum_minus_value"][1] is not None
```

Add these imports to the top of `test_intel.py` if absent:

```python
from unittest.mock import patch

from apps.market.services import intel as intel_mod
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose exec -T web pytest apps/market/tests/test_intel.py -k reuses_computed_legs -v`

Expected: FAIL — `assert 27 == 21` (each of the 3 spreads re-queries both legs: 18 extra).

- [ ] **Step 3: Reuse the computed legs**

In `backend/apps/market/services/intel.py`, replace the spreads loop in `factor_returns` with:

```python
    spreads: dict[str, dict[int, float | None]] = {}
    cache: dict[str, dict[int, float | None]] = dict(etf_rows)

    def _leg(ticker: str, window: int) -> float | None:
        row = cache.get(ticker.upper())
        if row is None:
            row = {w: return_over_sessions(ticker, w) for w in windows}
            cache[ticker.upper()] = row
        return row.get(window)

    for name, long_leg, short_leg in FACTOR_SPREADS:
        spreads[name] = {}
        for w in windows:
            lo, sh = _leg(long_leg, w), _leg(short_leg, w)
            spreads[name][w] = round(lo - sh, 4) if lo is not None and sh is not None else None
```

- [ ] **Step 4: Run the intel tests**

Run: `docker compose exec -T web pytest apps/market/tests/test_intel.py -v`

Expected: PASS (all, including the pre-existing shape/spread tests).

- [ ] **Step 5: Extract the events-window constant**

In `backend/apps/market/services/events.py`, above `upcoming_events`, add:

```python
# The forward window snapshots and the /api/market/events/ default both use.
# Duplicating the literal let the corporate-actions filter drift from the
# earnings/macro fetch — they must move together.
EVENTS_WINDOW_DAYS = 14
```

and change the signature to `within_days: int = EVENTS_WINDOW_DAYS`.

In `backend/apps/snapshots/services/__init__.py`, change `_fetch_events_section` to import
and use it:

```python
def _fetch_events_section(*, watchlist_tickers: list[str], **_) -> dict:
    import datetime as _dt

    from apps.market.models import CorporateAction
    from apps.market.services.events import EVENTS_WINDOW_DAYS

    data = upcoming_events(
        list(watchlist_tickers), within_days=EVENTS_WINDOW_DAYS, include_macro=True
    )
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
            ex_date__lte=today + _dt.timedelta(days=EVENTS_WINDOW_DAYS),
        ).order_by("ex_date")[:20]
    ]
    return {"data": data}
```

- [ ] **Step 6: Close the streamed Fed response**

In `backend/apps/market/services/fed.py`, replace the `_pull` body with:

```python
    def _pull() -> list[dict]:
        with requests.get(url, timeout=10, headers={"User-Agent": _UA}, stream=True) as resp:
            resp.raise_for_status()
            raw = resp.raw.read(_MAX_BYTES + 1, decode_content=True)
        if len(raw) > _MAX_BYTES:
            raise ValueError("feed exceeds size cap")
        return _parse(kind, raw)
```

- [ ] **Step 7: Comment the migration's noop reverse**

In `backend/apps/profiles/migrations/0013_backfill_default_includes.py`, replace the
`operations` list with:

```python
    operations = [
        # Reverse is a noop on purpose: once the kinds are in a profile's
        # default_includes there is no way to tell a backfilled kind from one
        # the user added themselves, so un-applying would silently delete the
        # user's own selections.
        migrations.RunPython(add_kinds, migrations.RunPython.noop),
    ]
```

- [ ] **Step 8: Run the affected suites**

Run: `docker compose exec -T web pytest apps/market/tests/test_intel.py apps/market/tests/test_events.py apps/market/tests/test_fed.py apps/snapshots/tests -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/apps/market/services/intel.py backend/apps/market/services/events.py backend/apps/market/services/fed.py backend/apps/snapshots/services/__init__.py backend/apps/profiles/migrations/0013_backfill_default_includes.py backend/apps/market/tests/test_intel.py
git commit -m "fix(market): reuse factor legs, share the events window, close the fed stream"
```

---

### Task 8: §5 serializer hygiene — treasury provenance, dead renderer entry, OHLC query budget

**Files:**
- Modify: `backend/apps/snapshots/serializer.py:1062-1084` (treasury), `:1142-1161` (`_RENDERERS`)
- Create: `backend/apps/snapshots/tests/test_ohlc_render_query_budget.py`
- Test: `backend/apps/snapshots/tests/test_serializer_treasury.py` (create if absent)

**Interfaces:**
- Produces: no new callables. `_RENDERERS` loses its `"ohlc"` key.

- [ ] **Step 1: Write the failing tests**

Create/append `backend/apps/snapshots/tests/test_serializer_treasury.py`:

```python
"""Treasury render: rates + debt, with the source's own record dates."""

from __future__ import annotations

from apps.snapshots.serializer import _render_treasury


def test_treasury_render_carries_record_date_provenance():
    """FiscalData's rates and debt publish on different schedules — without the
    as-of dates the AI reads two unrelated vintages as one snapshot."""
    md = _render_treasury(
        {
            "rates": {"record_date": "2026-08-31", "rates": {"Treasury Bills": 4.32}},
            "debt": {"record_date": "2026-09-18", "total_public_debt": 36_200_000_000_000.0},
        }
    )
    assert "as of 2026-08-31" in md
    assert "as of 2026-09-18" in md


def test_treasury_render_omits_missing_record_dates():
    md = _render_treasury({"rates": {"rates": {"Treasury Bills": 4.32}}, "debt": {}})
    assert "as of" not in md
    assert "| Treasury Bills | 4.32% |" in md
```

Create `backend/apps/snapshots/tests/test_ohlc_render_query_budget.py`:

```python
"""N+1 regression gate for the OHLC render's long-horizon block.

_render_ohlc(..., captured_at=...) calls _long_horizon_summary, which issues a
single bounded OHLCBar query regardless of how many bars or watchlist tickers
the payload carries. A budget of 2 leaves one slot of headroom while still
catching a per-bar or per-ticker N+1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.market.models import OHLCBar
from apps.snapshots.serializer import _render_ohlc


@pytest.mark.django_db
def test_render_ohlc_long_horizon_is_query_bounded(django_assert_max_num_queries):
    captured_at = datetime.now(UTC)
    OHLCBar.objects.bulk_create(
        OHLCBar(
            ticker="TST",
            timeframe="1d",
            ts=captured_at - timedelta(days=i + 1),
            open=100,
            high=101,
            low=99,
            close=100 + i * 0.1,
            volume=1_000,
        )
        for i in range(60)
    )
    payload = {
        "ticker": "TST",
        "timeframe": "1d",
        "bars": [
            {"ts": (captured_at - timedelta(days=i)).isoformat(), "open": 100, "high": 101,
             "low": 99, "close": 100, "volume": 1000}
            for i in range(30)
        ],
        "watchlist_daily": {
            "AAA": [{"ts": captured_at.isoformat(), "open": 1, "high": 1, "low": 1,
                     "close": 1, "volume": 1}],
            "BBB": [{"ts": captured_at.isoformat(), "open": 1, "high": 1, "low": 1,
                     "close": 1, "volume": 1}],
        },
    }

    with django_assert_max_num_queries(2):
        md = _render_ohlc(payload, captured_at=captured_at)

    assert "**Longer horizon (stored daily bars):**" in md
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose exec -T web pytest apps/snapshots/tests/test_serializer_treasury.py apps/snapshots/tests/test_ohlc_render_query_budget.py -v`

Expected: the treasury tests FAIL (`assert "as of 2026-08-31" in md`); the query-budget test
should PASS on first run — it is a *regression gate*, not a red test. If it fails, the
long-horizon block regressed and that is the real finding.

- [ ] **Step 3: Add the record-date provenance**

In `backend/apps/snapshots/serializer.py`, replace the body of `_render_treasury` after the
guard clauses with:

```python
    lines = ["## Treasury"]
    if rates:
        rates_asof = (payload.get("rates") or {}).get("record_date")
        heading = f"**Average interest rates** (as of {rates_asof})" if rates_asof else None
        if heading:
            lines.append(heading)
        lines += ["| Security | Avg rate |", "|---|---:|"]
        for security, rate in rates.items():
            lines.append(f"| {security} | {_fmt(rate)}% |")
    if total_debt is not None:
        debt_asof = debt.get("record_date")
        suffix = f" (as of {debt_asof})" if debt_asof else ""
        lines.append(f"- Debt to the penny: ${total_debt:,.0f}{suffix}")
    return "\n".join(lines)
```

Add to the docstring, after the payload-keys paragraph:

```
    The two sub-dicts publish on DIFFERENT schedules, so each carries its own
    record_date into the render — without it two vintages read as one snapshot.
```

- [ ] **Step 4: Remove the dead `_RENDERERS["ohlc"]` entry**

In `backend/apps/snapshots/serializer.py`, delete the `"ohlc": _render_ohlc,` line from
`_RENDERERS` and extend the neighbouring comment to:

```python
    # Neither "chain" nor "ohlc" is here: _render_included_section special-cases
    # both to pass captured_at through (chain's unusual-activity lookup, ohlc's
    # long-horizon stored-bar bound) — see the dispatch above.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `docker compose exec -T web pytest apps/snapshots/tests -q`

Expected: PASS. (If any test calls `_render_section("ohlc", …)` directly it will now get the
raw JSON dump — none does today; if one appears, point it at `_render_ohlc`.)

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_treasury.py backend/apps/snapshots/tests/test_ohlc_render_query_budget.py
git commit -m "fix(snapshots): treasury as-of provenance, drop the dead ohlc renderer entry"
```

---

### Task 9: Doc touchpoints

The follow-on doc lists these explicitly. README has **never** mentioned TradingView — the
architecture diagram, the app roster, the VIX bullet, the macro-seed sentence, and the
free-data-sources bullet all predate the integration.

**Files:**
- Modify: `README.md:59`, `:83`, `:126`, `:131`, `:132`
- Modify: `CLAUDE.md` (the capture-pipeline `vix` sentence)
- Modify: `FEATURES.md:78` area
- Modify: `docs/superpowers/specs/2026-09-19-macro-desk-follow-on-work.md`

- [ ] **Step 1: README — architecture diagram provider box (line 59)**

```
        market["Market data<br/>Schwab · TradingView (MCP) · Alpaca · Tiingo · Polygon · Tradier<br/>FRED · SEC EDGAR · Marketaux · US Treasury"]
```

- [ ] **Step 2: README — app roster (line 83)**

```
- `market` · Schwab client + TradingView (official MCP server) + free fallback providers (Alpaca / Tiingo / Twelve Data / Polygon / Tradier / FRED / SEC EDGAR / Marketaux / US Treasury), quotes/OHLC/chain/news, the forward-events calendar, shared forward-return helpers (`returns.py`)
```

- [ ] **Step 3: README — VIX bullet (line 126)**

Replace the "Without Schwab it degrades to spot-only" sentence with:

```
Without Schwab it degrades to spot plus the continuous front and second month when TradingView is connected, and to spot-only otherwise — with an explicit note either way, never silently omitted, and never pruned under token pressure.
```

- [ ] **Step 4: README — macro seed sentence (line 131)**

Replace "so on a free key the curated seed is the effective macro source" with:

```
so the macro calendar reads TradingView first when it's connected and falls back to the curated seed otherwise (FOMC dates through 2027; CPI / NFP / PCE / GDP through late 2026 until those calendars publish).
```

- [ ] **Step 5: README — free-data-sources bullet (line 132)**

Leave the free-provider list untouched and add a **separate** paragraph immediately after it:

```
- **TradingView (official MCP server)** — a **paid-plan** OAuth source, not a free one. When connected it is the *first* fallback for quotes / bars / news ahead of every free provider, and the macro-calendar source ahead of the curated seed. It adds instruments the free tier cannot quote: continuous **/VX** and **/VX2** VIX futures (the off-Schwab contango read), **$VVIX**, **$SKEW**, **$DXY**, the **2Y** Treasury tenor Schwab has no index for (which makes a live 2s10s computable), and **/ZQ** Fed funds futures. Breadth internals (`$ADVN`/`$DECN`/`$TICK`/`$TRIN`) have no TradingView equivalent and stay Schwab-only.
```

- [ ] **Step 6: CLAUDE.md — the `vix` capture sentence**

Find "free fallback providers can't quote CFE futures, so without Schwab it degrades to
spot-only with an explicit note (never silently omitted; not prunable by `token_budget`)"
and replace with:

```
TradingView quotes the continuous CFE legs (`/VX`→`CFE:VX1!`, `/VX2`→`CFE:VX2!`) so a TradingView-connected install keeps a contango read off-Schwab; the free providers can't quote CFE futures at all, so without either it degrades to spot-only with an explicit note (never silently omitted; not prunable by `token_budget`)
```

Then, in the TradingView bullet under "Data sources, predictions & coverage", append to the
symbol-mapping sentence:

```
The `$`-prefixed Treasury tenors map to the `TVC:US##Y` family, which publishes in **percent** while the app's `$`-yield convention is yield×10 — `tradingview._QUOTE_SCALE` restores the app unit at the provider boundary so `$TNX` means the same thing to `yields.py`, the breadth `MACRO` row, and a watchlist quote. `$US2Y` has no Schwab index at all, so `yields.live_yields` asks TradingView for it directly (`TV_ONLY_TENORS`) — the one deliberate per-symbol provider merge.
```

- [ ] **Step 7: FEATURES.md — free-data-sources bullet (line 78 area)**

Read the bullet and add one sentence in the same voice noting TradingView as a connected
paid source that outranks the free providers, adds the VIX-futures / VVIX / SKEW / DXY /
2Y / ZQ instruments, and is not part of the free tier.

- [ ] **Step 8: Update the follow-on doc itself**

In `docs/superpowers/specs/2026-09-19-macro-desk-follow-on-work.md`, replace §1's body with a
short "Shipped 2026-09-20" summary that records:
- what landed (the symbol rows, `_QUOTE_SCALE`, `$US2Y` + `TV_ONLY_TENORS`, the live 2s10s,
  `/VX2`, the aliases/root);
- the **design deviation**: the unit fix lives at the provider boundary, not as a
  per-provider divisor in `yields.py`, because `$TNX` has three consumers — `YIELD_INDICES`
  still carries `(tenor, divisor)` so each row states its unit;
- `$TNX` remapped from `TVC:TNX` to `TVC:US10Y` for one uniform tenor convention;
- what is **still owed by the user**: live-verify every new row (and its units) through
  `tv_get_symbol_data_batch` once TradingView is connected — nothing in this change could be
  verified against the live server;
- what was deliberately **not** built: the `/ZQ` strip render and the "Rec trend"
  fundamentals line (both need live TradingView result shapes first; the `/ZQ` symbol row
  landed so the contract is quotable).

Then mark the seven §5 fix-later items as done.

- [ ] **Step 9: Commit**

```bash
git add README.md CLAUDE.md FEATURES.md docs/superpowers/specs/2026-09-19-macro-desk-follow-on-work.md
git commit -m "docs: TradingView as a paid first-fallback source; Workstream E shipped"
```

---

### Task 10: Full gate run

- [ ] **Step 1: Lint**

Run: `docker compose exec -T -w /app web ruff check backend` then
`docker compose exec -T -w /app web ruff format --check backend`

Expected: clean. `factor_returns` gained a closure — confirm it stays under `ruff C901`
complexity 15.

- [ ] **Step 2: Types + architecture contracts**

Run: `docker compose exec -T -w /app web mypy backend` and
`docker compose exec -T -w /app web lint-imports`

Expected: zero mypy errors (zero baseline); import contracts intact. `yields.py` importing
`apps.market.services.tradingview` inside a function is same-app and allowed.

- [ ] **Step 3: Backend suite**

Run: `docker compose exec -T web pytest -q -p no:randomly`

Expected: PASS, coverage at or above `fail_under=86`.

- [ ] **Step 4: Schema drift**

Run: `make schema` then `git diff --stat backend/schema.yml`

Expected: no diff — nothing in this plan touches a serializer field or endpoint.

- [ ] **Step 5: Commit any gate-driven fixes**

```bash
git add -A ':!compose.yaml' ':!compose.prod.yaml'
git commit -m "chore: gate fixes for the macro-desk follow-on"
```

Leave `compose.yaml` / `compose.prod.yaml` alone — they carry unrelated uncommitted work
(the restart-policy move to the prod overlay) that predates this plan.

---

## Self-Review

**Spec coverage (§1 Workstream E):**
- Symbol-map rows (`$VVIX`, `$DXY` + alias, `$IRX/$FVX/$TYX`, `$US2Y`, `$SKEW`, `/ZQ`) — Tasks 2, 3.
- The yields unit contract blocker — Tasks 1, 2 (boundary scale + per-row divisor).
- `$US2Y` scoping / the per-symbol provider merge — Task 4; the live 2s10s payoff — Task 5.
- Optional `/VX2` — Task 6. Optional "Rec trend" line and `/ZQ` strip render — **deliberately
  deferred** (documented in Task 9 Step 8): both need live TradingView result shapes, and
  TradingView is not connected here.
- Post-merge doc touchpoints — Task 9.

**Spec coverage (§5 fix-later):** factor legs (7), events window (7), treasury `record_date`
(8), `profiles/0013` comment (7), `fed.py` `with` (7), dead `_RENDERERS["ohlc"]` (8), OHLC
query-budget test (8). All seven covered.

**§2/§3/§4** are coordination notes, dispositioned items, and learnings — no tasks by design.

**Type consistency:** `YIELD_INDICES` is `dict[str, tuple[str, float]]` in Tasks 1 and 4;
`_QUOTE_SCALE` is `dict[str, float]` in Task 2 and referenced by that name in Tasks 1 and 9;
`TV_ONLY_TENORS` is `frozenset[str]` in Task 4 and named identically in Task 9;
`second["continuous"]` is set in Task 6 Step 3 and read in Task 6 Step 4.
