# Market-Data Depth — derived "intel" enrichment — design

**Date:** 2026-05-29
**Status:** Approved (pending spec review)
**Topic:** The capture pipeline fetches rich raw data but hands the AI thin gruel: sector ETFs as bare last-prices, no relative strength, no IV context. The derivable intelligence is discarded. This spec adds a derived **`intel`** snapshot section, computed once at capture from data the pipeline already fetches or stores: **sector rotation**, **relative strength vs SPY**, and an **IV-rank / skew / term-structure** summary. It compounds the Decision Coach (richer current context to go with the new memory). Scope = derived-only, **no new vendor**.

## Problem

The capture pipeline pulls sector ETFs, OHLC, and option chains, then throws away the intelligence sitting in that data:

- **Sector rotation is one projection away.** `apps/market/services/context.py:23` (`_last`) keeps only `last` and discards the `pct_change` that `fetch_quotes` already returns for every sector ETF. The AI sees 11 sector last-prices it can do nothing with.
- **No relative strength.** Whether the snapshot's ticker is leading or lagging the market — the most basic context for a directional read — is absent, despite `fetch_ohlc` upserting daily bars into `OHLCBar`.
- **No IV context.** `apps/analytics/services/unusual_options.py` already computes a 30-day IV mean/stdev from the stored `OptionChainSnapshot` history, but that lives in a post-hoc analytics page; the chain the AI sees carries no "is today's IV high or low" signal.

The audit's framing: run the cheap analytics *into* the snapshot at capture time, not just on-demand after. Nothing here is net-new analytics — it's composition of existing helpers.

## Non-goals (YAGNI)

- **No new vendor / fundamentals / short interest.** Finnhub `/stock/metric` (P/E, market cap, short interest) is deferred to a follow-up spec — it needs a new vendor call + model + migration.
- **RS "vs the ticker's own sector ETF" is deferred** — it needs a ticker→sector map we can't derive without a vendor. Market-wide sector **rotation** still tells the AI which sectors lead; RS is **vs SPY** only.
- **No `diff_sections` branch for `intel`.** It's silently not diffed today (`_diff_one` returns "" for unknown kinds) — acceptable; a later add.
- **No composer/frontend work** beyond the snapshots browser showing an `intel` section chip (add a label if a kind→label map exists). `intel` is **auto-derived**, never user-selectable in `includes`.
- **No new toggle.** Enrichment is default-on, gated per input section (below).
- **No technical-indicator additions** (SMA/RSI/ATR exist as a tool; out of scope here).

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Derived-only: rotation + RS-vs-SPY + IV-rank/skew/term | Cheap, no vendor, compounds the Decision Coach now |
| Surface | A dedicated persisted `intel` **section** (not augment breadth/chain, not serialize-time) | Clean isolated unit; computed once at capture + persisted (visible in browser/diff, reusable by the Coach); RS has a natural home; doesn't entangle derived with raw data |
| Placement | Post-loop step in `capture_for_existing`, after `primary_ticker` is set; purely additive | RS needs `primary_ticker` (known only after the section loop); must not affect `ok_count`/status |
| Gating | rotation ⟺ `breadth` in includes · RS ⟺ `primary_ticker` set · IV ⟺ `chain` in includes **and** `primary_ticker` | Each enrichment ties to a user-requested input — no surprise I/O on minimal captures; empty → no section |
| RS source | Compute from the daily bars `fetch_ohlc(.., "1d", 25)` returns (ticker + SPY) | Self-contained; `fetch_ohlc` upserts to `OHLCBar` so it doubles as history; simpler than timestamp helpers |
| IV stats | Extract `iv_values`/`parse_iv` public in `unusual_options` (keep `iv_stats` on top); `intel` reuses them for z + percentile | DRY (repo's shared-helper convention, à la `returns.py`) |
| Failure mode | `enrich_snapshot` never raises; each computation independently guarded; empty → no section | Additive on the capture hot path — a bug costs the intel section, never the capture |

## Architecture

```
 capture_for_existing (apps/snapshots/services/__init__.py)
   for kind in snap.includes: fetch raw sections …
   snap.primary_ticker = …                                   ← known here
   enrich_snapshot(snap)   ───────────────────────────────┐  ← NEW (additive, never raises)
   snap.status = "ready" if ok_count>0 else "failed"       │
                                                           ▼
 enrich_snapshot(snap)  (apps/snapshots/services/enrich.py)
   payload = build_intel_payload(snap):
     rotation  = sector_rotation()                if "breadth" in snap.includes
     rel_str   = relative_strength(primary)       if snap.primary_ticker
     iv        = iv_summary(primary, at=now)       if "chain" in snap.includes and primary
   if any present → SnapshotSection(kind="intel", payload, status="done") + stamp tokens
                                                           │
   analytics (apps/market/services/intel.py):              │
     sector_rotation()  → fetch_quotes(SECTOR_ETFS) ranked by pct_change
     relative_strength(t)→ fetch_ohlc(t,"1d",25) + fetch_ohlc("SPY","1d",25), %Δ over 5/20 sessions
     iv_summary(t, at)  → latest+30d OptionChainSnapshot, ATM IV z/percentile/skew/term (iv_stats)
                                                           ▼
 serialize_for_ai(snap):  render includes … then append _render_intel(intel.payload)  (always; small)
   → coached run = 🧭 coach block + objective/sections + ## Market intelligence
```

### 1. Analytics — `apps/market/services/intel.py` (new)

```python
def sector_rotation() -> dict | None
def relative_strength(ticker: str, *, benchmark: str = "SPY", windows: tuple[int, ...] = (5, 20)) -> dict | None
def iv_summary(ticker: str, *, at: datetime) -> dict | None
```

- **`sector_rotation`** — `fetch_quotes(SECTOR_ETFS)` (the 11 `XL*` from `context.py`; cached). Build `{"ranked": [{"etf","sector","pct"}…]}` sorted by `pct_change` desc; ETFs with no `pct_change` are dropped. A module-level `_SECTOR_NAMES = {"XLK":"Technology", …}` supplies readable names. Returns `None` if the fetch yields nothing.
- **`relative_strength`** — `fetch_ohlc(ticker, timeframe="1d", bars=25)` and `fetch_ohlc(benchmark, timeframe="1d", bars=25)` (both upsert to `OHLCBar`). Sort bars ascending by `ts`; for each window `N`, `pct = (bars[-1].close − bars[-1-N].close)/bars[-1-N].close*100` when `len(bars) > N`. Returns `{"ticker","benchmark","windows":[{"days":N,"ticker_pct","benchmark_pct","rs_pct"}…]}`, a window present only with enough bars; `None` if the ticker has no bars.
- **`iv_summary`** — latest `OptionChainSnapshot(ticker, fetched_at<=at)` + 30-day prior history (mirrors `unusual_options`); returns `None` for a falsy ticker or when no chain snapshot exists. From the latest payload: ATM strike = nearest to `underlying_last` in the front (lowest) expiry; `atm_iv` from that strike; `z` (sigmas vs the 30-day mean/stdev) and `percentile` (fraction of 30-day IVs ≤ `atm_iv`); `skew` = ATM put IV − call IV; `term` = front-expiry ATM IV vs next-expiry ATM IV → `shape` ("backwardation" if front>next, else "contango"). Every field best-effort (`None` when not computable).
- **IV-stats extraction (DRY):** extract the IV-collection loop as public `iv_values(history) -> list[float]` and `parse_iv(raw)` in `unusual_options.py`; rebuild `iv_stats(history)` (mean/stdev) on top of `iv_values` and keep `unusual_options` using `iv_stats`. `iv_summary` imports `iv_values`/`parse_iv` and computes mean/stdev (→ `z`) + `percentile` from the one list. Mirrors the repo's shared-helper convention (à la `returns.py`).

### 2. Orchestration — `apps/snapshots/services/enrich.py` (new)

```python
def build_intel_payload(snap) -> dict:
    """Gated, best-effort. Returns {} when nothing applies/computes."""
    payload = {}
    if "breadth" in snap.includes:
        payload["rotation"] = _safe(sector_rotation)
    if snap.primary_ticker:
        payload["relative_strength"] = _safe(lambda: relative_strength(snap.primary_ticker))
    if "chain" in snap.includes and snap.primary_ticker:
        payload["iv"] = _safe(lambda: iv_summary(snap.primary_ticker, at=timezone.now()))
    return {k: v for k, v in payload.items() if v}   # drop None/empty

def enrich_snapshot(snap) -> None:
    """Write a SnapshotSection(kind='intel') from build_intel_payload. NEVER raises."""
```

- `_safe(fn)` returns `fn()` or `None` on any exception (logged) — same discipline as `apps/briefing/services/assemble._safe`.
- `enrich_snapshot` is wrapped in a top-level `try/except` (log + return). If `build_intel_payload` is empty, it writes **no** section. Otherwise `SnapshotSection.objects.update_or_create(snapshot=snap, kind="intel", defaults={"payload":…, "status":"done"})` then `stamp_payload_tokens(section)`.
- **Wiring:** in `capture_for_existing`, call `enrich_snapshot(snap)` immediately after `snap.primary_ticker = …` and before the status line. It does not touch `ok_count`.

### 3. Model — `apps/snapshots/models.py`

Add `("intel", "Market intel")` to `SnapshotSection.KIND_CHOICES`. A choices-only `AlterField` migration (DB `varchar` unchanged) — mirrors the `threads.Thread.kind="diff"` precedent. No data migration.

### 4. Renderer + serialize integration — `apps/snapshots/serializer.py`

- Add `_render_intel(payload)` and `"intel": "Market intel"` to `_title`; register `_render_intel` in `_RENDERERS`. Output (each block omitted when its key is absent):

  ```
  ## Market intelligence

  ### Sector rotation (today)
  XLK Technology +1.8% · XLF Financials +0.9% · … · XLE Energy −1.2%   (leaders → laggards)

  ### NVDA relative strength vs SPY
  - 5d: NVDA +3.9% vs SPY +1.2% → +2.7% RS (outperforming)
  - 20d: NVDA +8.0% vs SPY +3.0% → +5.0% RS (outperforming)

  ### NVDA implied volatility
  - ATM IV 54% — 1.2σ above the 30-day mean (48%), ~85th pct → elevated
  - Skew: puts +3 vol over calls (downside bid)
  - Term: front 54% vs next 49% → backwardation (front-loaded event premium)
  ```

- **Render even though `intel` isn't in `includes`:** in `serialize_for_ai`, after the `includes` loop + `prune_to_budget` + the pruned-kinds note, look up `sections_by_kind.get("intel")` and, if present with a non-empty payload, append `_render_intel(sec.payload)` to `parts`. It is small (~a few hundred tokens) and **always included** — not a prune candidate — like the market-state banner.

### 5. Error handling

Covered above: `_safe` per computation, top-level guard in `enrich_snapshot`, empty→no section, gating prevents surprise I/O. Under `MOCK_EXTERNAL`, `fetch_quotes`/`fetch_ohlc` short-circuit to canned fixtures, so E2E captures get a deterministic `intel` section. `OptionChainSnapshot` reads return `None` cleanly when no chain exists.

### 6. Testing (favoring `pytest.mark.parametrize`)

- **`apps/market/tests/test_intel.py`** — `sector_rotation` (patch `fetch_quotes` → ranked desc + sector names; empty → None); `relative_strength` (patch `fetch_ohlc` → window math + `rs_pct`; `len(bars) <= N` → window omitted; no ticker bars → None); `iv_summary` (build `OptionChainSnapshot` latest+history → `z`/`percentile`/`skew`/`term`; no chain → None; <2 historical IVs → stats `None`, no crash).
- **`apps/analytics/tests/test_unusual_options.py`** — still green after the `iv_values`/`parse_iv` extraction (existing tests are the guard); add a direct `iv_values` test if not already covered.
- **`apps/snapshots/tests/test_enrich.py`** — gating matrix (breadth-only → `rotation` only; quotes+chain → all three with computes mocked; positions-only → **no `intel` section**); never-raises (monkeypatch one computation to throw → others still written, capture still `ready`); section is `status="done"` with tokens stamped.
- **Serializer test** — a snapshot with an `intel` section → `serialize_for_ai` contains `## Market intelligence` + content; without one → output unchanged.
- **Capture integration** — `capture_for_existing` (fetchers mocked) writes the `intel` section when inputs present and leaves `status="ready"`/`ok_count` unaffected.

### 7. Migration & ops

- One reversible choices-only `AlterField` on `SnapshotSection.kind`. No data migration.
- **No new Celery task/beat → no `worker`/`beat` restart.** No new dependency, credential, or vendor.
- Adds (gated, cached) `fetch_quotes(SECTOR_ETFS)` + two daily `fetch_ohlc` per context-bearing capture — negligible at single-user scale; a small capture-latency add.
- Honors the silent-failure landmines: section terminal state `"done"`; no direct provider instantiation; no secret logging.

## Implementation order (for the plan)

1. `apps/market/services/intel.py` → `sector_rotation` + the `_SECTOR_NAMES` map + tests.
2. Extract `iv_values`/`parse_iv` public in `unusual_options.py` (rebuild `iv_stats` on `iv_values`, update callers); `iv_summary` in `intel.py` + tests; confirm `test_unusual_options` green.
3. `relative_strength` in `intel.py` + tests.
4. `SnapshotSection.kind` "intel" choices migration; `apps/snapshots/services/enrich.py` (`_safe`, `build_intel_payload`, `enrich_snapshot`) + gating/never-raises tests.
5. Wire `enrich_snapshot` into `capture_for_existing`; capture-integration test (additive, status unaffected).
6. `_render_intel` + `_title` + `serialize_for_ai` intel-append + serializer tests.

Steps 1–3 are independent (parallelizable); 4 depends on 1–3; 5 depends on 4; 6 depends on 4 (needs the section) and is otherwise independent.
