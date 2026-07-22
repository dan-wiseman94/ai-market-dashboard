# Snapshot Data-Quality Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the nine data-quality defects found in the 2026-07-22 audit of snapshot #17 (see memory `snapshot-data-quality-audit-2026-07`): OHLC token bloat, prune cascade, dead macro events, Finnhub key leaking into logs/section errors, Finnhub/EDGAR symbol collisions, futures chain 400s, unbounded chain expirations, stale EDGAR filings, and premarket junk values.

**Architecture:** Small targeted changes to `apps/market` services (symbol gating, scrubbing, bounded fetches) plus `apps/snapshots` (capture fetcher selection, serializer shrink-before-prune, premarket banner). One new helper per concern, reused across call sites: `symbols.is_equity_like`, `safe_log.scrub_secret_params`. No schema changes, no new deps, no API-shape changes.

**Tech Stack:** Django 5 / DRF, pytest (`docker compose exec web pytest …`, WORKDIR `/app/backend` so paths drop the `backend/` prefix), unittest.mock at the SDK/HTTP boundary, fakeredis via existing fixtures.

## Global Constraints

- Tests must pass before commit; run targeted files then the app suites (`apps/market`, `apps/snapshots`).
- Working tree already has uncommitted changes on `fix/architecture-review` — do NOT commit, revert, or reformat unrelated files. No commits at all unless the user asks.
- Never log or persist strings that may embed `token=`/`apikey=`/`api_key=` query params (CLAUDE.md security landmine).
- Follow existing patterns: services never grow new abstractions; `safe_err` is the precedent for log scrubbing.
- Out of code scope (user action required, report at end): enable "Accounts and Trading Production" on the Schwab developer portal (positions 401); rotate the Finnhub API key (already leaked to local logs).
- After implementation: `docker compose restart worker beat` (stale-worker landmine), then live-verify with `market.refresh_events` + a `serialize_for_ai` probe.

---

### Task 1: `symbols.is_equity_like` gate

**Files:**
- Modify: `backend/apps/market/symbols.py` (append function)
- Test: `backend/apps/market/tests/test_symbols.py` (append)

**Produces:** `is_equity_like(symbol: str) -> bool` — True only for plain stock/ETF symbols safe to send to equity-only providers (Finnhub company endpoints, EDGAR). False for `""`, `$`-prefixed, `/`-prefixed, bare index aliases (`SPX`), bare futures roots (`ES`, `NQ`).

- [x] Test first (parametrized: `QQQ/AAPL/spy → True`; `ES/NQ//ESU26/$SPX/SPX/VX/"" → False`), run to fail, implement, pass.

```python
def is_equity_like(symbol: str) -> bool:
    """True when `symbol` is a plain stock/ETF suitable for equity-only providers
    (Finnhub company endpoints, SEC EDGAR). Futures (bare root or /-prefixed) and
    cash indices ($-prefixed or bare alias) resolve to instruments those providers
    either don't know or — worse — collide with an unrelated equity (bare "ES" is
    Eversource Energy on Finnhub while the rest of this app treats it as /ES)."""
    s = (symbol or "").strip().upper()
    if not s or s.startswith(("$", "/")):
        return False
    return s not in INDEX_ALIASES and s not in FUTURE_ROOTS
```

### Task 2: secret scrubbing — `scrub_secret_params` + capture-boundary + Finnhub log sites

**Files:**
- Modify: `backend/apps/market/services/safe_log.py` (append function)
- Modify: `backend/apps/market/services/events.py:223` and `:263` (use `safe_err`)
- Modify: `backend/apps/market/services/fundamentals.py:111` (use `safe_err`)
- Modify: `backend/apps/market/services/corporate_actions.py` (any raw-exc log sites → `safe_err`)
- Modify: `backend/apps/snapshots/services/__init__.py:239` (`section.error` through `scrub_secret_params`)
- Test: `backend/apps/market/tests/test_safe_log.py`, `backend/apps/snapshots/tests/test_capture.py` (append)

**Produces:** `scrub_secret_params(text: str) -> str` — masks values of `token`/`apikey`/`api_key`/`key` query params anywhere in a string, keeping the rest of the message intact (section errors stay diagnostic — the audit relied on the full chain URL).

```python
_SECRET_PARAMS = re.compile(r"(?i)\b(token|apikey|api_key|key)=([^&\s\"']+)")

def scrub_secret_params(text: str) -> str:
    """Mask credential-bearing query params inside `text` (e.g. a requests
    exception message embedding the full URL). Unlike `safe_err` this keeps the
    surrounding message — use it where the text is user-facing diagnostics
    (SnapshotSection.error) rather than a log line."""
    return _SECRET_PARAMS.sub(r"\1=***", text)
```

Capture loop change: `section.error = scrub_secret_params(f"{type(exc).__name__}: {exc}")`.
Capture test: fetcher raising `RuntimeError("boom https://x/api?token=SECRET&a=1")` → stored error contains `token=***`, not `SECRET`.

### Task 3: macro events — refreshed seed + no-upcoming warning

**Files:**
- Modify: `backend/apps/market/services/events_seed.py` (replace list: FOMC decision days Jul 29 18:00, Sep 16 18:00, Oct 28 18:00, Dec 9 19:00 UTC; CPI Aug 12/Sep 11/Oct 13 12:30, Nov 10/Dec 10 13:30 UTC; NFP Aug 7/Sep 4/Oct 2 12:30, Nov 6/Dec 4 13:30 UTC — published Fed/BLS 2026 schedules, EDT→EST shift; keep the "MUST be verified" caveat)
- Modify: `backend/apps/market/services/events.py` `fetch_macro` — after fallback upsert, `log.warning` when no row has `event_time` in the future (the seed has gone stale again)
- Test: `backend/apps/market/tests/test_events_service.py` (append: seed contains ≥1 event after 2026-07-22 — frozen reference date, not `now()`; warning fires when all upserted events are past)

### Task 4: Finnhub/EDGAR symbol gating

**Files:**
- Modify: `backend/apps/market/services/events.py` — `fetch_earnings` filters `[t for t in tickers if is_equity_like(t)]`; `upcoming_events` on-demand fill skips non-equity tickers
- Modify: `backend/apps/market/services/news.py` — company-news loop iterates only `is_equity_like` tickers (general news unchanged)
- Modify: `backend/apps/market/services/fundamentals.py` — `fetch_fundamentals` returns `{}` early for non-equity
- Modify: `backend/apps/market/services/edgar.py` — `fetch_filings`/`fetch_insider` return `[]` early for non-equity (before mock-mode canned fixtures? NO — keep mock behavior for arbitrary tickers; guard after the mock branch)
- Modify: `backend/apps/snapshots/services/__init__.py` — `filings` fetcher dict-comprehension filters `is_equity_like(t)` (no bogus "NQ" keys in payload)
- Tests: append to `test_events_service.py`, `test_news_service.py`, `test_fundamentals_service.py`, `test_edgar.py` — assert "ES"/"NQ"/"/NQ"/"$SPX" trigger no HTTP call and produce empty results; equities unaffected.

**Consumes:** Task 1 `is_equity_like`.

### Task 5: EDGAR recency cutoff

**Files:**
- Modify: `backend/apps/market/services/edgar.py` — `fetch_filings(..., max_age_days: int = 548)`; `_normalize_filings` gains `min_filed: str` (ISO date, lexicographic compare) and skips older rows; same for `fetch_insider`/`_normalize_insider`.
- Test: `backend/apps/market/tests/test_edgar.py` (append: submissions fixture with a 2014 and a recent filing → only the recent one returned; `max_age_days=None`-style bypass not needed — YAGNI).

### Task 6: capture fetcher — chain-capable symbol selection

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` — new `_pick_chain_ticker(watchlist) -> str | None`: first ticker whose `normalize_symbol` does not start with `/` (cash indices like `$SPX` DO have chains — snapshot #16 proves it; only futures are chain-incapable). `_FETCHERS["chain"]` uses it; when None, raise `ValueError("no chain-capable symbol in watchlist (futures contracts have no equity option chain)")` so the section fails with a self-explanatory error instead of a Schwab 400.
- Test: `backend/apps/snapshots/tests/test_capture_extended.py` (append): watchlist `["NQ","QQQ"]` → chain fetched for `QQQ`; watchlist `["NQ"]` → section failed with the explanatory error, no Schwab call.

### Task 7: chain expiration bound

**Files:**
- Modify: `backend/apps/market/services/chain.py` — `fetch_chain(..., within_days: int = 60)`; pass `from_date=date.today()`, `to_date=date.today() + timedelta(days=within_days)` to `client.get_option_chain`; include `within_days` in the cache-key params hash.
- Test: `backend/apps/market/tests/test_chain_service.py` (append: asserts `from_date`/`to_date` kwargs and hash change).

### Task 8: quotes hygiene (zero high/low, futures pct_change)

**Files:**
- Modify: `backend/apps/market/services/quotes.py` `_fetch_from_schwab` row post-processing:
  - `high`/`low` `0` → `None` when `last` is truthy (Schwab placeholder before the day session).
  - `pct_change` fallback chain: `netPercentChange` → `futurePercentChange` → computed `(last-closePrice)/closePrice*100` when both present and `closePrice` truthy.
- Test: `backend/apps/market/tests/test_services_quotes.py` (append: premarket ETF quote normalizes zeros; futures quote with only `closePrice` gets computed pct; genuine intraday high/low preserved).

### Task 9: breadth internals gate

**Files:**
- Modify: `backend/apps/market/services/context.py` `_fetch` — after building `breadth`, drop it entirely when `($ADVN + $DECN) < 100` (Schwab returns placeholder internals before ~9:30 ET; 8 advancers vs 0 decliners is the tape warming up, not breadth).
- Test: `backend/apps/market/tests/test_services_context.py` (append: degenerate internals → `breadth == {}`; populated internals pass through).

### Task 10: OHLC fine-window cap (the bloat fix)

**Files:**
- Modify: `backend/apps/market/services/ohlc.py` — `_FINE_WINDOW = timedelta(hours=4)`; `_fetch_24h_from_schwab` computes `fine_start = max(start_dt, session_open, end_dt - _FINE_WINDOW)`; non-1m unchanged; 1m fetches 5m over `[start_dt, fine_start)` (filter `ts < fine_start`) + 1m over `[fine_start, end_dt]`; single-resolution short-circuit when `fine_start <= start_dt`. This uniformly bounds futures sessions (~23h), equity premarket captures (yesterday's full session), and weekends — worst case ≈ 240 × 1m + ~240 × 5m ≈ 480 bars, matching `_ALT_24H_LIMIT["1m"]`.
- Modify: `backend/apps/snapshots/serializer.py` `_render_ohlc` header copy: `" — last 24h (1m recent, 5m earlier)"`.
- Tests: update `backend/apps/market/tests/test_services_ohlc_24h.py` (blend test boundary moves from `session_open` to `end-4h`; weekend test now coarsens — 5m called; add a futures-length-session case) and `backend/apps/snapshots/tests/test_serializer_24h.py` (header copy).

### Task 11: serializer shrink-before-prune + prune reorder

**Files:**
- Modify: `backend/apps/snapshots/token_budget.py` — `_PRUNE_ORDER = ["chain", "ohlc", "news", "breadth", "quotes", "positions"]` (never sacrifice news to save an oversized OHLC).
- Modify: `backend/apps/snapshots/serializer.py` — before `prune_to_budget`, if total estimate exceeds `max_tokens` and an `ohlc` section rendered: truncate `payload["bars"]` to the newest `k` (proportional to the token headroom × 0.9 safety, floor 30) and re-render with a `truncated_from` marker line `_(showing newest k of N bars — older bars trimmed to fit the token budget)_`; loop at most 3 halvings while still over. Keep `prune_to_budget` as the final safety net.
- Tests: update `test_token_budget.py` order pin; append serializer test: oversized-ohlc snapshot serialized at small budget keeps news + a truncated OHLC tail (newest bars) with the marker; generous budget unchanged.

### Task 12: premarket banner in serializer

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` — after the market-closed banner: when `market_state.markets.us_equity.phase` is `premarket`/`postmarket`, append `> **Market state:** US equities in <phase> — day-session fields (day high/low, breadth internals) may be incomplete.`
- Test: `backend/apps/snapshots/tests/test_serializer_market_banner.py` (append).

### Task 13: docs + live verification

- Modify: `CLAUDE.md` — update the two lines that became false: capture-pipeline OHLC note (1m recent 4h / 5m earlier, not "current session"), data-sources landmine (macro seed must be refreshed periodically; Finnhub economic calendar is premium → 403 on free tier).
- `docker compose restart worker beat`; run `apps/market` + `apps/snapshots` suites; `make lint` scope-checked (`ruff` + `mypy` on backend); `/conventions-check`.
- Live verify: `market.refresh_events` seeds upcoming macro; `serialize_for_ai(Snapshot 17)` still renders (old payloads unaffected); fresh capture for `["NQ","QQQ"]` exercises chain-fallback + filings gate + ohlc cap end-to-end.

## Self-Review

- All 9 audit findings map to tasks (1→10/11, 2→11, 3→3, 4→2, 5→4, 6→6, 7→out-of-scope user action, 8→5, 9→8/9/12); chain-expiry bloat (audit prose) → 7.
- Names consistent: `is_equity_like`, `scrub_secret_params`, `_FINE_WINDOW`, `_pick_chain_ticker`, `within_days`.
- No placeholders; test updates reference exact existing tests read during planning.
