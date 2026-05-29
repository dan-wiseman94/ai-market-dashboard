# Market-Data Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a derived `intel` snapshot section — sector rotation, relative strength vs SPY, and an IV z-score/percentile/skew/term-structure summary — computed once at capture from data the pipeline already fetches or stores (no new vendor), so the AI (and the Decision Coach) reasons over richer current context.

**Architecture:** Pure analytics live in a new `apps/market/services/intel.py` (snapshot-agnostic, each returns a dict or `None`). A new `apps/snapshots/services/enrich.py` orchestrates them (gated per input section, best-effort, never-raises) and writes a `SnapshotSection(kind="intel")`. `capture_for_existing` calls it post-loop (after `primary_ticker` is known); `serialize_for_ai` renders the intel section even though it isn't in `includes`.

**Tech Stack:** Django + DRF, Celery, Postgres, pytest. Reuses `fetch_quotes` (rotation `pct_change`), `fetch_ohlc` (RS daily bars), and an extracted `iv_values`/`parse_iv` from `unusual_options` (IV).

---

## Conventions for every task

- **Run backend tests** in the live container (worktree `backend/` is bind-mounted at `/app/backend`, WORKDIR `/app/backend`): `docker exec snaptr-web-1 pytest apps/<app>/tests/test_x.py -v`.
- **makemigrations** must run as uid 1000 so the file is host-writable: `docker exec -u 1000:1000 snaptr-web-1 python manage.py makemigrations <app>`; apply with `docker exec snaptr-web-1 python manage.py migrate`. If a test fails with "no such column"/stale test DB, re-run pytest with `--create-db`.
- **git** runs on the HOST in `/home/dan/ai-dashboard/.claude/worktrees/snap-triggers-recall`. You are already on branch `feat/snap-triggers-recall-impl`. Only `git add`/`git commit` — no other git commands. If the pre-commit hook fails on container-relative paths (known worktree no-`.env` bug), prefix the commit with `LEFTHOOK=0`. End commit messages with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **Guardrails:** use the provided test + implementation code verbatim; never weaken/skip/xfail a test to go green — if a test reveals a real problem, report BLOCKED. `ty` is advisory; gates are `ruff` + `pytest`.

---

## File Structure

**Create:**
- `backend/apps/market/services/intel.py` — `sector_rotation()`, `relative_strength(...)`, `iv_summary(...)` + helpers + `_SECTOR_NAMES`.
- `backend/apps/market/tests/test_intel.py` — unit tests for the three analytics.
- `backend/apps/snapshots/services/enrich.py` — `_safe`, `build_intel_payload(snap)`, `enrich_snapshot(snap)`.
- `backend/apps/snapshots/tests/test_enrich.py` — gating + never-raises + section-write tests.
- `backend/apps/snapshots/migrations/00NN_section_kind_intel.py` — generated (choices `AlterField`).

**Modify:**
- `backend/apps/analytics/services/unusual_options.py` — extract public `iv_values`/`parse_iv`; rebuild `_iv_stats` on `iv_values`.
- `backend/apps/snapshots/models.py` — add `("intel", "Market intel")` to `SnapshotSection.KIND_CHOICES`.
- `backend/apps/snapshots/services/__init__.py` — call `enrich_snapshot(snap)` post-loop in `capture_for_existing`.
- `backend/apps/snapshots/serializer.py` — `_render_intel` + `_title["intel"]` + `_RENDERERS` + the intel append in `serialize_for_ai`.

---

## Task 1: `sector_rotation` + the analytics module

**Files:** Create `backend/apps/market/services/intel.py`; Create `backend/apps/market/tests/test_intel.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/market/tests/test_intel.py`:

```python
from __future__ import annotations

from unittest.mock import patch

from apps.market.services.intel import sector_rotation


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_ranks_desc_with_sector_names(mock_fq):
    mock_fq.return_value = {
        "XLK": {"last": 1, "pct_change": 1.8},
        "XLF": {"last": 1, "pct_change": 0.9},
        "XLE": {"last": 1, "pct_change": -1.2},
    }
    out = sector_rotation()
    assert [r["etf"] for r in out["ranked"]] == ["XLK", "XLF", "XLE"]
    assert out["ranked"][0] == {"etf": "XLK", "sector": "Technology", "pct": 1.8}
    assert out["ranked"][-1]["pct"] == -1.2


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_drops_none_pct_and_empty_is_none(mock_fq):
    mock_fq.return_value = {"XLK": {"pct_change": None}, "XLF": {}}
    assert sector_rotation() is None
```

- [ ] **Step 2: Run test to verify it fails** — `docker exec snaptr-web-1 pytest apps/market/tests/test_intel.py -v`. Expected: FAIL — `ModuleNotFoundError: apps.market.services.intel`.

- [ ] **Step 3: Create `backend/apps/market/services/intel.py`:**

```python
"""Derived market intelligence: sector rotation, relative strength, IV summary.

Pure analytics composed from data the capture pipeline already fetches or
stores. Snapshot-agnostic; each public function returns a plain dict or None.
"""

from __future__ import annotations

from apps.market.services.context import SECTOR_ETFS
from apps.market.services.quotes import fetch_quotes

_SECTOR_NAMES = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLY": "Cons. Disc.",
    "XLP": "Cons. Staples",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Comm. Svcs.",
}


def sector_rotation() -> dict | None:
    """Rank the 11 sector ETFs by today's % change (leaders → laggards)."""
    quotes = fetch_quotes(SECTOR_ETFS)
    ranked: list[dict] = []
    for etf in SECTOR_ETFS:
        pct = (quotes.get(etf) or {}).get("pct_change")
        if pct is None:
            continue
        ranked.append({"etf": etf, "sector": _SECTOR_NAMES.get(etf, etf), "pct": round(float(pct), 2)})
    if not ranked:
        return None
    ranked.sort(key=lambda r: r["pct"], reverse=True)
    return {"ranked": ranked}
```

- [ ] **Step 4: Run test to verify it passes** — `docker exec snaptr-web-1 pytest apps/market/tests/test_intel.py -v`. Expected: PASS (2).

- [ ] **Step 5: Commit**
```bash
git add backend/apps/market/services/intel.py backend/apps/market/tests/test_intel.py
git commit -m "feat(market): sector_rotation analytic for the intel section" \
           -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: extract `iv_values`/`parse_iv`, add `iv_summary`

**Files:** Modify `backend/apps/analytics/services/unusual_options.py`; Modify `backend/apps/market/services/intel.py`; Modify `backend/apps/market/tests/test_intel.py`.

- [ ] **Step 1: Write the failing test** — append to `backend/apps/market/tests/test_intel.py` (add the imports to the top import block, then the helpers + tests):

```python
# add to top imports:
from datetime import UTC, datetime, timedelta

import pytest

from apps.market.models import OptionChainSnapshot
from apps.market.services.intel import iv_summary
```

```python
def _chain(ticker, *, when, expiries):
    """expiries: {exp: {"calls": [line...], "puts": [line...]}}; line = {"strike","iv",...}."""
    snap = OptionChainSnapshot.objects.create(
        ticker=ticker,
        expiries=list(expiries.keys()),
        payload={"underlying_last": "100.00", "expiries": expiries, "ticker": ticker},
    )
    OptionChainSnapshot.objects.filter(id=snap.id).update(fetched_at=when)
    return snap


def _ln(strike, iv):
    return {"strike": strike, "iv": iv, "bid": "1.0", "ask": "1.1", "volume": 1, "oi": 1}


@pytest.mark.django_db
def test_iv_summary_z_percentile_skew_term():
    now = datetime(2026, 4, 10, tzinfo=UTC)
    # 30-day history: ATM call IV cycles 0.28..0.32 → mean ~0.30
    for d in range(30):
        iv = f"{0.28 + 0.01 * (d % 5):.3f}"
        _chain("AAPL", when=now - timedelta(days=30 - d),
               expiries={"2026-05-15": {"calls": [_ln("100.00", iv)], "puts": [_ln("100.00", iv)]}})
    # latest: elevated front IV 0.50, front put 0.53 (skew +0.03), next expiry 0.45 (backwardation)
    _chain("AAPL", when=now, expiries={
        "2026-05-15": {"calls": [_ln("100.00", "0.50")], "puts": [_ln("100.00", "0.53")]},
        "2026-06-19": {"calls": [_ln("100.00", "0.45")], "puts": [_ln("100.00", "0.45")]},
    })
    out = iv_summary("AAPL", at=now)
    assert out["ticker"] == "AAPL"
    assert out["atm_iv"] == 0.50
    assert out["z"] is not None and out["z"] > 5            # 0.50 is far above the ~0.30 mean
    assert out["percentile"] == 1.0                          # 0.50 >= every historical IV
    assert out["skew"] == pytest.approx(0.03, abs=1e-9)
    assert out["term"]["shape"] == "backwardation"
    assert out["term"]["front_iv"] == 0.50 and out["term"]["next_iv"] == 0.45


@pytest.mark.django_db
def test_iv_summary_none_when_no_chain():
    assert iv_summary("ZZZZ", at=datetime(2026, 4, 10, tzinfo=UTC)) is None


@pytest.mark.django_db
def test_iv_summary_none_for_falsy_ticker():
    assert iv_summary("", at=datetime(2026, 4, 10, tzinfo=UTC)) is None
```

- [ ] **Step 2: Run test to verify it fails** — `docker exec snaptr-web-1 pytest apps/market/tests/test_intel.py -k iv_summary -v`. Expected: FAIL — `ImportError: cannot import name 'iv_summary'`.

- [ ] **Step 3: Extract public helpers in `unusual_options.py`.** In `backend/apps/analytics/services/unusual_options.py`, rename `_parse_iv`→`parse_iv` and add `iv_values`, and rebuild `_iv_stats` on top. Replace the existing `_parse_iv` and `_iv_stats` definitions with:

```python
def parse_iv(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def iv_values(history: list[OptionChainSnapshot]) -> list[float]:
    """All parseable IV values across the historical chain snapshots."""
    ivs: list[float] = []
    for snap in history:
        expiries = (snap.payload or {}).get("expiries") or {}
        for sides in expiries.values():
            for side_key in ("calls", "puts"):
                for line in sides.get(side_key, []) or []:
                    iv = parse_iv(line.get("iv"))
                    if iv is not None:
                        ivs.append(iv)
    return ivs


def _iv_stats(history: list[OptionChainSnapshot]) -> tuple[float | None, float | None]:
    """Mean + stdev of IV values across the historical chain snapshots."""
    ivs = iv_values(history)
    if len(ivs) < 2:
        return (None, None)
    return (statistics.mean(ivs), statistics.stdev(ivs))
```

Then update the one internal caller of `_parse_iv` (in `_score_line`) to `parse_iv`:

```python
    iv = parse_iv(line.get("iv"))
```

(`statistics` is already imported at the top of the file.)

- [ ] **Step 4: Add `iv_summary` to `intel.py`.** Append to `backend/apps/market/services/intel.py`:

```python
def _to_float(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _atm_iv(lines: list[dict], underlying: float | None, parse_iv) -> float | None:
    """IV of the contract whose strike is nearest `underlying`."""
    if underlying is None:
        return None
    best = None
    for line in lines or []:
        strike = _to_float(line.get("strike"))
        if strike is None:
            continue
        dist = abs(strike - underlying)
        if best is None or dist < best[0]:
            best = (dist, parse_iv(line.get("iv")))
    return best[1] if best else None


def iv_summary(ticker: str, *, at) -> dict | None:
    """ATM IV z-score + percentile (vs 30-day history) + skew + term structure.

    Returns None for a falsy ticker, no chain snapshot, or when ATM IV is
    indeterminable. Best-effort per field.
    """
    import statistics
    from datetime import timedelta

    from apps.analytics.services.unusual_options import iv_values, parse_iv
    from apps.market.models import OptionChainSnapshot

    if not ticker:
        return None
    ticker = ticker.upper()
    latest = (
        OptionChainSnapshot.objects.filter(ticker=ticker, fetched_at__lte=at)
        .order_by("-fetched_at")
        .first()
    )
    if latest is None:
        return None
    payload = latest.payload or {}
    expiries = payload.get("expiries") or {}
    if not expiries:
        return None
    underlying = _to_float(payload.get("underlying_last"))
    exps = sorted(expiries.keys())
    front = expiries[exps[0]]
    front_call = _atm_iv(front.get("calls"), underlying, parse_iv)
    front_put = _atm_iv(front.get("puts"), underlying, parse_iv)
    atm_iv = front_call if front_call is not None else front_put
    if atm_iv is None:
        return None

    result: dict = {"ticker": ticker, "atm_iv": round(atm_iv, 4)}

    history = list(
        OptionChainSnapshot.objects.filter(
            ticker=ticker,
            fetched_at__gte=at - timedelta(days=30),
            fetched_at__lt=latest.fetched_at,
        ).order_by("fetched_at")
    )
    ivs = iv_values(history)
    if len(ivs) >= 2:
        mean = statistics.mean(ivs)
        stdev = statistics.stdev(ivs)
        result["mean_30d"] = round(mean, 4)
        if stdev:
            result["z"] = round((atm_iv - mean) / stdev, 2)
        result["percentile"] = round(sum(1 for v in ivs if v <= atm_iv) / len(ivs), 2)

    if front_put is not None and front_call is not None:
        result["skew"] = round(front_put - front_call, 4)

    if len(exps) >= 2:
        nxt = expiries[exps[1]]
        next_iv = _atm_iv(nxt.get("calls"), underlying, parse_iv)
        if next_iv is None:
            next_iv = _atm_iv(nxt.get("puts"), underlying, parse_iv)
        if next_iv is not None:
            result["term"] = {
                "front": exps[0],
                "front_iv": round(atm_iv, 4),
                "next": exps[1],
                "next_iv": round(next_iv, 4),
                "shape": "backwardation" if atm_iv > next_iv else "contango",
            }
    return result
```

- [ ] **Step 5: Run tests to verify they pass** — `docker exec snaptr-web-1 pytest apps/market/tests/test_intel.py apps/analytics/tests/test_unusual_options.py -v`. Expected: PASS (intel iv_summary tests + the existing unusual_options tests still green after the extraction).

- [ ] **Step 6: Commit**
```bash
git add backend/apps/analytics/services/unusual_options.py backend/apps/market/services/intel.py \
        backend/apps/market/tests/test_intel.py
git commit -m "feat(market): iv_summary (z/percentile/skew/term); extract iv_values/parse_iv (DRY)" \
           -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `relative_strength`

**Files:** Modify `backend/apps/market/services/intel.py`; Modify `backend/apps/market/tests/test_intel.py`.

- [ ] **Step 1: Write the failing test** — append to `backend/apps/market/tests/test_intel.py`:

```python
from apps.market.services.intel import relative_strength  # add to top imports


def _daily(closes: list[float]) -> list[dict]:
    return [
        {"ts": f"2026-05-{1 + i:02d}T00:00:00+00:00", "open": c, "high": c, "low": c, "close": c, "volume": 1}
        for i, c in enumerate(closes)
    ]


@patch("apps.market.services.intel.fetch_ohlc")
def test_relative_strength_5d_window(mock_ohlc):
    def side_effect(ticker, *, timeframe, bars):
        if ticker == "NVDA":
            return _daily([100, 100, 100, 100, 100, 103.9])   # +3.9% over 5 sessions
        return _daily([100, 100, 100, 100, 100, 101.2])        # SPY +1.2%
    mock_ohlc.side_effect = side_effect
    out = relative_strength("NVDA")
    assert out["ticker"] == "NVDA" and out["benchmark"] == "SPY"
    assert out["windows"] == [
        {"days": 5, "ticker_pct": 3.9, "benchmark_pct": 1.2, "rs_pct": 2.7}
    ]  # 20d omitted (only 6 bars)


@patch("apps.market.services.intel.fetch_ohlc")
def test_relative_strength_none_when_no_ticker_bars(mock_ohlc):
    mock_ohlc.return_value = []
    assert relative_strength("NVDA") is None


def test_relative_strength_none_for_falsy_ticker():
    assert relative_strength("") is None
```

- [ ] **Step 2: Run test to verify it fails** — `docker exec snaptr-web-1 pytest apps/market/tests/test_intel.py -k relative_strength -v`. Expected: FAIL — `ImportError: cannot import name 'relative_strength'`.

- [ ] **Step 3: Implement.** Add the `fetch_ohlc` import to the top of `intel.py` (next to the other `apps.market.services` imports):

```python
from apps.market.services.ohlc import fetch_ohlc
```

Append to `intel.py`:

```python
def _window_pct(bars: list[dict], n: int) -> float | None:
    if len(bars) <= n:
        return None
    prev = _to_float(bars[-1 - n].get("close"))
    cur = _to_float(bars[-1].get("close"))
    if prev is None or cur is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100.0, 2)


def relative_strength(
    ticker: str, *, benchmark: str = "SPY", windows: tuple[int, ...] = (5, 20)
) -> dict | None:
    """Ticker vs benchmark % change over each window (sessions), from daily bars."""
    if not ticker:
        return None
    t_bars = sorted(fetch_ohlc(ticker, timeframe="1d", bars=25), key=lambda b: b["ts"])
    if not t_bars:
        return None
    b_bars = sorted(fetch_ohlc(benchmark, timeframe="1d", bars=25), key=lambda b: b["ts"])
    windows_out: list[dict] = []
    for n in windows:
        tp = _window_pct(t_bars, n)
        if tp is None:
            continue
        bp = _window_pct(b_bars, n)
        windows_out.append(
            {
                "days": n,
                "ticker_pct": tp,
                "benchmark_pct": bp,
                "rs_pct": round(tp - bp, 2) if bp is not None else None,
            }
        )
    if not windows_out:
        return None
    return {"ticker": ticker, "benchmark": benchmark, "windows": windows_out}
```

(`_to_float` already exists from Task 2.)

- [ ] **Step 4: Run tests to verify they pass** — `docker exec snaptr-web-1 pytest apps/market/tests/test_intel.py -v`. Expected: PASS (all).

- [ ] **Step 5: Commit**
```bash
git add backend/apps/market/services/intel.py backend/apps/market/tests/test_intel.py
git commit -m "feat(market): relative_strength vs benchmark from daily bars" \
           -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `intel` section kind + `enrich_snapshot`

**Files:** Modify `backend/apps/snapshots/models.py`; Create migration; Create `backend/apps/snapshots/services/enrich.py`; Create `backend/apps/snapshots/tests/test_enrich.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/snapshots/tests/test_enrich.py`:

```python
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.services.enrich import enrich_snapshot


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s")


def _snap(profile, *, includes, primary="NVDA") -> Snapshot:
    return Snapshot.objects.create(
        profile=profile, status="ready", includes=includes, source="manual", primary_ticker=primary
    )


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.iv_summary")
@patch("apps.snapshots.services.enrich.relative_strength")
@patch("apps.snapshots.services.enrich.sector_rotation")
def test_enrich_writes_gated_parts(mock_rot, mock_rs, mock_iv, profile):
    mock_rot.return_value = {"ranked": [{"etf": "XLK", "sector": "Technology", "pct": 1.0}]}
    mock_rs.return_value = {"ticker": "NVDA", "benchmark": "SPY", "windows": []}
    mock_iv.return_value = {"ticker": "NVDA", "atm_iv": 0.5}

    snap = _snap(profile, includes=["quotes", "breadth", "chain"])
    enrich_snapshot(snap)

    sec = SnapshotSection.objects.get(snapshot=snap, kind="intel")
    assert sec.status == "done"
    assert set(sec.payload) == {"rotation", "relative_strength", "iv"}


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.iv_summary")
@patch("apps.snapshots.services.enrich.relative_strength")
@patch("apps.snapshots.services.enrich.sector_rotation")
def test_enrich_positions_only_writes_no_section(mock_rot, mock_rs, mock_iv, profile):
    # No breadth, no chain, no primary_ticker → nothing applies.
    snap = _snap(profile, includes=["positions"], primary=None)
    enrich_snapshot(snap)
    assert not SnapshotSection.objects.filter(snapshot=snap, kind="intel").exists()
    mock_rot.assert_not_called()
    mock_rs.assert_not_called()
    mock_iv.assert_not_called()


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.relative_strength", side_effect=RuntimeError("boom"))
@patch("apps.snapshots.services.enrich.sector_rotation")
def test_enrich_never_raises_and_keeps_healthy_parts(mock_rot, mock_rs, profile):
    mock_rot.return_value = {"ranked": [{"etf": "XLK", "sector": "Technology", "pct": 1.0}]}
    snap = _snap(profile, includes=["quotes", "breadth"])
    enrich_snapshot(snap)  # must not raise despite relative_strength throwing
    sec = SnapshotSection.objects.get(snapshot=snap, kind="intel")
    assert set(sec.payload) == {"rotation"}  # rs failed → dropped; rotation kept
```

- [ ] **Step 2: Run test to verify it fails** — `docker exec snaptr-web-1 pytest apps/snapshots/tests/test_enrich.py -v`. Expected: FAIL — `ModuleNotFoundError: apps.snapshots.services.enrich` (and the `intel` kind not yet allowed).

- [ ] **Step 3: Add the `intel` kind.** In `backend/apps/snapshots/models.py`, add to `SnapshotSection.KIND_CHOICES` (after `("overnight", "Overnight board")`):

```python
        ("intel", "Market intel"),
```

- [ ] **Step 4: Generate + apply the migration**
```bash
docker exec -u 1000:1000 snaptr-web-1 python manage.py makemigrations snapshots
docker exec snaptr-web-1 python manage.py migrate snapshots
```
Expected: a single choices-only `AlterField` on `snapshotsection.kind`. Open the generated file and confirm it's only that.

- [ ] **Step 5: Create `backend/apps/snapshots/services/enrich.py`:**

```python
"""Derived 'intel' snapshot enrichment: sector rotation + relative strength + IV summary.

Runs post-capture (after primary_ticker is known). Additive and best-effort: a
failure here costs the intel section, never the capture.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.market.services.intel import iv_summary, relative_strength, sector_rotation
from apps.snapshots.models import SnapshotSection

log = logging.getLogger(__name__)


def _safe(fn):
    try:
        return fn()
    except Exception:
        log.warning("intel.section_failed", exc_info=True)
        return None


def build_intel_payload(snap) -> dict:
    """Gated, best-effort. Returns {} when nothing applies or computes."""
    payload: dict = {}
    if "breadth" in snap.includes:
        payload["rotation"] = _safe(sector_rotation)
    if snap.primary_ticker:
        payload["relative_strength"] = _safe(lambda: relative_strength(snap.primary_ticker))
    if "chain" in snap.includes and snap.primary_ticker:
        payload["iv"] = _safe(lambda: iv_summary(snap.primary_ticker, at=timezone.now()))
    return {k: v for k, v in payload.items() if v}


def enrich_snapshot(snap) -> None:
    """Write a SnapshotSection(kind='intel') from build_intel_payload. NEVER raises."""
    try:
        payload = build_intel_payload(snap)
        if not payload:
            return
        from apps.snapshots.services import stamp_payload_tokens

        section, _ = SnapshotSection.objects.update_or_create(
            snapshot=snap,
            kind="intel",
            defaults={"payload": payload, "status": "done", "error": ""},
        )
        stamp_payload_tokens(section)
    except Exception:
        log.warning("intel.enrich_failed", exc_info=True)
```

- [ ] **Step 6: Run tests to verify they pass** — `docker exec snaptr-web-1 pytest apps/snapshots/tests/test_enrich.py -v`. Expected: PASS (3).

- [ ] **Step 7: Commit**
```bash
git add backend/apps/snapshots/models.py backend/apps/snapshots/migrations/ \
        backend/apps/snapshots/services/enrich.py backend/apps/snapshots/tests/test_enrich.py
git commit -m "feat(snapshots): intel section kind + enrich_snapshot (gated, never-raises)" \
           -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: wire `enrich_snapshot` into capture

**Files:** Modify `backend/apps/snapshots/services/__init__.py`; Modify `backend/apps/snapshots/tests/test_enrich.py`.

- [ ] **Step 1: Write the failing test** — append to `backend/apps/snapshots/tests/test_enrich.py`:

```python
from apps.snapshots.services import capture_for_existing  # add to top imports


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.relative_strength", return_value=None)
@patch("apps.snapshots.services.enrich.iv_summary", return_value=None)
@patch("apps.snapshots.services.enrich.sector_rotation")
@patch("apps.snapshots.services.fetch_market_context")
def test_capture_adds_intel_section_and_stays_ready(mock_ctx, mock_rot, *_, profile):
    mock_ctx.return_value = {"spx_last": 1, "qqq_last": 1, "vix_last": 1, "sectors": {}, "breadth": {}}
    mock_rot.return_value = {"ranked": [{"etf": "XLK", "sector": "Technology", "pct": 1.0}]}
    snap = Snapshot.objects.create(
        profile=profile, status="pending", includes=["breadth"], source="manual"
    )
    capture_for_existing(snap)
    snap.refresh_from_db()
    assert snap.status == "ready"
    sec = SnapshotSection.objects.get(snapshot=snap, kind="intel")
    assert "rotation" in sec.payload
```

- [ ] **Step 2: Run test to verify it fails** — `docker exec snaptr-web-1 pytest apps/snapshots/tests/test_enrich.py -k capture_adds_intel -v`. Expected: FAIL — no `intel` section (enrich not wired into capture yet).

- [ ] **Step 3: Wire it in.** In `backend/apps/snapshots/services/__init__.py`, add the import near the other `apps.snapshots.*` imports at the top:

```python
from apps.snapshots.services.enrich import enrich_snapshot
```

Then in `capture_for_existing`, immediately after the `snap.primary_ticker = ...` line and before the `snap.status = ...` line, add:

```python
        enrich_snapshot(snap)
```

So the tail reads:
```python
        snap.primary_ticker = derive_primary_ticker(snap) if _primary is None else _primary
        enrich_snapshot(snap)
        snap.status = "ready" if (ok_count > 0 or attached_client_images) else "failed"
```

- [ ] **Step 4: Run tests to verify they pass** — `docker exec snaptr-web-1 pytest apps/snapshots/tests/test_enrich.py -v`. Expected: PASS (4).

- [ ] **Step 5: Commit**
```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tests/test_enrich.py
git commit -m "feat(snapshots): run enrich_snapshot post-capture (additive)" \
           -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: render the intel section into the AI payload

**Files:** Modify `backend/apps/snapshots/serializer.py`; Modify (or create) `backend/apps/snapshots/tests/test_serializer_intel.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/snapshots/tests/test_serializer_intel.py`:

```python
from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import serialize_for_ai


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s")


@pytest.mark.django_db
def test_serialize_renders_intel_section(profile):
    snap = Snapshot.objects.create(
        profile=profile, status="ready", includes=["breadth"], source="manual", primary_ticker="NVDA"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="breadth", status="done",
        payload={"spx_last": 1, "qqq_last": 1, "vix_last": 1, "sectors": {}, "breadth": {}},
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="intel", status="done",
        payload={
            "rotation": {"ranked": [{"etf": "XLK", "sector": "Technology", "pct": 1.8},
                                     {"etf": "XLE", "sector": "Energy", "pct": -1.2}]},
            "relative_strength": {"ticker": "NVDA", "benchmark": "SPY",
                                   "windows": [{"days": 5, "ticker_pct": 3.9, "benchmark_pct": 1.2, "rs_pct": 2.7}]},
            "iv": {"ticker": "NVDA", "atm_iv": 0.54, "mean_30d": 0.48, "z": 1.2,
                   "percentile": 0.85, "skew": 0.03,
                   "term": {"front": "2026-06-05", "front_iv": 0.54, "next": "2026-06-12",
                            "next_iv": 0.49, "shape": "backwardation"}},
        },
    )
    out = serialize_for_ai(snap)
    assert "## Market intelligence" in out
    assert "XLK" in out and "Technology" in out
    assert "relative strength vs SPY" in out.lower() or "RS" in out
    assert "NVDA" in out and "54" in out          # ATM IV rendered
    assert "backwardation" in out


@pytest.mark.django_db
def test_serialize_without_intel_is_unchanged(profile):
    snap = Snapshot.objects.create(
        profile=profile, status="ready", includes=["breadth"], source="manual"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="breadth", status="done",
        payload={"spx_last": 1, "qqq_last": 1, "vix_last": 1, "sectors": {}, "breadth": {}},
    )
    assert "## Market intelligence" not in serialize_for_ai(snap)
```

- [ ] **Step 2: Run test to verify it fails** — `docker exec snaptr-web-1 pytest apps/snapshots/tests/test_serializer_intel.py -v`. Expected: FAIL — no `## Market intelligence` (renderer + append not added).

- [ ] **Step 3: Add the renderer.** In `backend/apps/snapshots/serializer.py`:

(a) add `"intel": "Market intel"` to the `_title` dict;

(b) add `_render_intel` (place it near the other `_render_*` functions):

```python
def _render_intel(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    blocks: list[str] = ["## Market intelligence"]

    rot = payload.get("rotation")
    if rot and rot.get("ranked"):
        cells = [f"{r['etf']} {r.get('sector', '')} {_fmt(r.get('pct'))}%" for r in rot["ranked"]]
        blocks.append("### Sector rotation (today)\n" + " · ".join(cells) + "   (leaders → laggards)")

    rs = payload.get("relative_strength")
    if rs and rs.get("windows"):
        lines = [f"### {rs.get('ticker', '?')} relative strength vs {rs.get('benchmark', 'SPY')}"]
        for w in rs["windows"]:
            rs_pct = w.get("rs_pct")
            tag = ""
            if rs_pct is not None:
                tag = " (outperforming)" if rs_pct > 0 else " (lagging)" if rs_pct < 0 else ""
            lines.append(
                f"- {w.get('days')}d: {rs.get('ticker')} {_fmt(w.get('ticker_pct'))}% vs "
                f"{rs.get('benchmark')} {_fmt(w.get('benchmark_pct'))}% → {_fmt(rs_pct)}% RS{tag}"
            )
        blocks.append("\n".join(lines))

    iv = payload.get("iv")
    if iv and iv.get("atm_iv") is not None:
        lines = [f"### {iv.get('ticker', '?')} implied volatility"]
        bits = [f"ATM IV {_fmt(iv.get('atm_iv'))}"]
        if iv.get("z") is not None:
            bits.append(f"{_fmt(iv.get('z'))}σ vs 30-day mean ({_fmt(iv.get('mean_30d'))})")
        if iv.get("percentile") is not None:
            bits.append(f"{_fmt(iv.get('percentile'))} pctile")
        lines.append("- " + ", ".join(bits))
        if iv.get("skew") is not None:
            lines.append(f"- Skew (put−call ATM): {_fmt(iv.get('skew'))}")
        term = iv.get("term")
        if term:
            lines.append(
                f"- Term: front {_fmt(term.get('front_iv'))} vs next {_fmt(term.get('next_iv'))} "
                f"→ {term.get('shape')}"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if len(blocks) > 1 else ""
```

(c) register it in `_RENDERERS`:

```python
    "intel": _render_intel,
```

(d) in `serialize_for_ai`, after the pruned-kinds note block (the `if pruned_kinds:` lines) and before `return "\n\n".join(parts)...`, append the intel section (rendered even though it's not in `includes`; guarded against double-render):

```python
    intel_sec = sections_by_kind.get("intel")
    if intel_sec is not None and intel_sec.status == "done" and intel_sec.payload and "intel" not in snapshot.includes:
        intel_md = _render_intel(intel_sec.payload)
        if intel_md:
            parts.append(intel_md)
```

- [ ] **Step 4: Run tests to verify they pass** — `docker exec snaptr-web-1 pytest apps/snapshots/tests/test_serializer_intel.py -v`. Expected: PASS (2).

- [ ] **Step 5: Full regression + lint**
```bash
docker exec snaptr-web-1 pytest apps/market apps/snapshots apps/analytics -q
docker exec snaptr-web-1 ruff check apps/market apps/snapshots apps/analytics
```
Expected: all pass; ruff clean. (`test_snapshot_injection`, `test_overnight_model`, `test_explain_diff` etc. unaffected — intel only appears when a section is written, which existing fixtures don't trigger.)

- [ ] **Step 6: Commit**
```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_intel.py
git commit -m "feat(snapshots): render the intel section into the AI payload" \
           -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- §1 `sector_rotation` → Task 1 ✅ · `relative_strength` → Task 3 ✅ · `iv_summary` + `iv_values`/`parse_iv` extraction → Task 2 ✅
- §2 `build_intel_payload`/`enrich_snapshot` + gating (breadth / primary_ticker / chain+primary_ticker) + never-raises + empty→no section → Task 4 ✅
- §2 capture wiring (post-`primary_ticker`, additive) → Task 5 ✅
- §3 `intel` KIND_CHOICES + choices migration → Task 4 ✅
- §4 `_render_intel` + `_title` + `_RENDERERS` + serialize append (not-in-includes) → Task 6 ✅
- §5 error handling (`_safe`, top-level guard, gating) → Tasks 2/4 ✅
- §6 testing (rotation/RS/IV units; unusual_options still green; enrich gating+never-raises; capture integration; serializer) → Tasks 1–6 ✅
- §7 migration/ops (one choices AlterField; no beat/worker restart) → Task 4 ✅

**2. Placeholder scan:** No TBD/TODO; every step has complete code; the migration is generated with a verification step (Task 4 Step 4). The illustrative renderer numbers are in test fixtures, not implementation.

**3. Type/name consistency:** `sector_rotation()→{"ranked":[{"etf","sector","pct"}]}`, `relative_strength()→{"ticker","benchmark","windows":[{"days","ticker_pct","benchmark_pct","rs_pct"}]}`, `iv_summary()→{"ticker","atm_iv","mean_30d","z","percentile","skew","term":{front,front_iv,next,next_iv,shape}}` are used identically in `_render_intel` (Task 6) and the enrich/serializer tests. `_to_float` is defined once (Task 2) and reused (Task 3). `iv_values`/`parse_iv` signatures match between Task 2's extraction and `iv_summary`'s import. `enrich_snapshot`/`build_intel_payload` patch targets (`apps.snapshots.services.enrich.*`) are consistent across Tasks 4–5.

**Note for the implementer:** Tasks 1–3 are independent (parallelizable); Task 4 depends on 1–3; Task 5 depends on 4; Task 6 depends on 4 (needs the section) + is otherwise independent. Each task is independently testable and shippable.
