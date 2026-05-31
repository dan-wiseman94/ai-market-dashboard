# C3 — Corporate-Action Adjustment in the Returns Math — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use subagent-driven-development or executing-plans. Steps use `- [ ]` tracking.

**Goal:** Stop stock splits (and, opt-in, dividends) from corrupting forward-return math — a 3:1 split must read as ~0%, not −66%.

**Architecture:** Corporate actions are sourced from Finnhub (`/stock/split`, `/stock/dividend`), stored in a new `CorporateAction` table (mirrors `MarketEvent`), and applied **at read time** in `apps/market/returns.py` as a non-destructive cumulative adjustment. Stored `OHLCBar` rows are never rewritten — the frozen-at-capture record is the whole point of a post-mortem; adjusting at read time keeps it intact and reversible. Splits are always adjusted (a split is a pure non-event for the holder, so an unadjusted return is simply wrong). Dividends convert price-return → total-return, a semantic change, so they sit behind a default-off `RETURNS_ADJUST_DIVIDENDS` setting (matching the repo's `OBSERVER_RESPONSE_CACHE_ENABLED` / `AI_FAILOVER_ENABLED` opt-in convention).

**Tech Stack:** Django, Postgres, Celery beat, Redis cache, Finnhub REST, pytest.

## The math (start-share basis)

A holder of 1 share at `start`. A split at ex-date `s` with ratio `r = shares_after/shares_before` multiplies share count by `r` and divides price by `r`. To compare the `end` price to `start` on the same basis:

- **Split factor** `F = Π r_i` over splits with `start < ex_date_i ≤ end`.
- **Adjusted end value** (per start-share) `= end_close × F`.
- `return_pct = (end_close × F − start_close) / start_close × 100`.
  - 3:1 split (`r=3`): start $300, end $100 → `(100×3 − 300)/300 = 0%`. ✓
  - 1:10 reverse (`r=0.1`): start $5, end $50 → `(50×0.1 − 5)/5 = 0%`. ✓
- **No splits → `F = 1.0`**, identical to today's output (zero behaviour change on the common path).
- **Dividends (opt-in)** add `Σ amount_i × Π(r_j for splits with start < ex_j ≤ ex_i)` to the end value (each dividend scaled onto the start-share basis).

`max_high`/`min_low` in `price_path_summary` are brought onto the start basis by segmenting the window at each split ex-date (constant cumulative factor per segment); these feed only the AI narrative, not the verdict, so the segmenting is for honest display.

## File structure

- `backend/apps/market/models.py` — add `CorporateAction`.
- `backend/apps/market/migrations/0008_corporateaction.py` — new table.
- `backend/apps/market/services/corporate_actions.py` — Finnhub fetch + upsert + `corporate_actions_for()` read (+ on-demand fill), mock-mode canned.
- `backend/apps/market/returns.py` — `split_factor()`, `dividend_adjustment()`, wire the 3 window functions.
- `backend/apps/market/cache.py` — `"corporate_actions"` TTL kind.
- `backend/apps/market/tasks.py` — `market.refresh_corporate_actions`.
- `backend/config/celery.py` — daily beat entry.
- `backend/config/settings/base.py` — `RETURNS_ADJUST_DIVIDENDS` (default False).
- `backend/apps/core/mocks/...` — canned split for mock-mode.
- Tests: `apps/market/tests/test_returns_corporate_actions.py`, `test_corporate_actions_service.py`.

## Tasks

### Task 1: `CorporateAction` model + migration
Fields: `source`, `external_id` (uniq w/ source), `kind` (`split|dividend`), `ticker`, `ex_date` (DateField), `ratio` (Decimal null — splits), `amount` (Decimal null — dividends), `detail` (JSON), `fetched_at`. Indexes `(ticker, ex_date)`, `(kind, ex_date)`. Migrate as uid 1000 so the file is dan-owned.

### Task 2: `split_factor()` + returns wiring (TDD — the core)
- [ ] Test: a 3:1 split between start and end makes `forward_return_pct` read ~0 (raw −66%).
- [ ] Test: reverse split; multiple splits multiply; no splits → unchanged (factor 1.0).
- [ ] Test: `trading_day_forward_return_pct` adjusts on `t1`.
- [ ] Test: `price_path_summary` return_pct adjusted; max/min on start basis.
- [ ] Implement `split_factor(ticker, after, until)`, wire the 3 functions.

### Task 3: dividend opt-in
- [ ] Test: with `RETURNS_ADJUST_DIVIDENDS=True`, a dividend in-window lifts the return; default off = no change.

### Task 4: Finnhub service + mock-mode
- [ ] Test (mock-mode): `fetch_splits`/`fetch_dividends` upsert canned rows; `corporate_actions_for` reads them; idempotent re-fetch.
- [ ] Implement service cloning `events.py` (key, list-returning GET, cache, upsert, on-demand fill).

### Task 5: beat task + settings + cache kind
- [ ] `refresh_corporate_actions` task; beat entry; `corporate_actions` TTL (86400); `RETURNS_ADJUST_DIVIDENDS` setting.

### Task 6: verify + commit + PR
- [ ] Run `apps/market` + `apps/thesis` + `apps/analytics` + `apps/triggers` tests in-container; ruff; commit; push; PR.
