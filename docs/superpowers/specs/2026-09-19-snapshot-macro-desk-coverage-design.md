# Snapshot Macro-Desk Coverage — Design

**Written 2026-09-19.** Close the gaps found by the 2026-09-19 snapshot-coverage audit, which
graded the capture pipeline against a 16-category "full macro-desk picture" wishlist
(ES/NQ/SPY/QQQ price action, breadth, VIX/VVIX, yields+curve, DXY, credit spreads, sector
performance, factor returns, options positioning, gamma estimates, flows, economic releases,
Fed communication, earnings/news, analyst revisions, historical price data) and found
**0 fully covered, 11 partial, 5 missing**. Two root causes explain most of the "partial"s:

1. **Delivery, not data** — the default capture is `['quotes','positions','breadth']`
   (+ always-on `vix`); rich sections (macro, events, news, chain, ohlc) exist but are opt-in,
   and the profile editor UI can only select 5 of the 15 section kinds.
2. **Computed but discarded** — several signals are already fetched or calculated and then
   dropped before the render: per-strike dealer GEX, sector-ETF 1-day % change,
   `eps_actual`/`rev_est`, per-strike volume/OI, the unusual-options scan.

This spec fixes both, adds the missing data that flows through existing integrations
(credit spreads, VVIX, dollar, factor returns, deeper history), and builds the three
genuinely new surfaces the user approved: a `fed` section (Fed communication), a `flowlite`
section (an honest volume-based flow proxy), and Form 4 insider filings.

## 1. Decisions (locked 2026-09-19 — don't re-ask)

- **Rich defaults everywhere**: `ohlc`, `chain`, `news`, `events`, `macro` join
  `DEFAULT_INCLUDES`, with a data migration so existing profiles get them. The observer-cost
  consequence is documented in §9 and guarded by the existing cost caps — **note:** the
  figure quoted when this was decided ($6.5/day) was corrected upward 3–10× in spec review
  (§9); the decision stands subject to reaffirmation at the spec-review gate.
- **All three new surfaces**: `fed` section, `flowlite` section, Form 4 into `filings`.
- **TradingView symbol-map rows land in this spec as post-merge tasks** (§7) — no changes to
  the in-flight `worktree-tradingview-mcp` branch.
- **Sequencing**: this work lands **after** the TradingView MCP branch merges
  (`docs/superpowers/specs/2026-09-19-tradingview-mcp-design.md`; implementation in
  progress on `worktree-tradingview-mcp`). The actual file intersection is small —
  `apps/secrets/data_sources.py` (different regions) plus §7's hard dependency on the
  merged `tradingview.py` symbol map; the TV branch touches neither `vix.py`, `context.py`,
  nor `fred.py`, and this spec touches neither `events.py` nor `fallback.py`'s TV wiring
  (C7 adjusts `alt_bars` parameter conversion only).

## 2. Files touched

| Concern | Files |
|---|---|
| Defaults + migration | `backend/apps/profiles/models.py`, new data migration in `apps/profiles/migrations/` |
| FE section ceilings | `frontend/src/pages/profiles/types.ts`, `ProfileForm.tsx`, `SnapshotSectionPicker.tsx`, `SchedulesPage.tsx`, `frontend/src/api/observer.ts` |
| Render fixes | `backend/apps/snapshots/serializer.py`, `backend/apps/market/services/option_analytics.py`, `context.py` |
| New quote/FRED data | `backend/apps/market/services/fred.py`, `vix.py`, `context.py`, `intel.py`, `tasks.py` (`ingest_daily_bars`), `ohlc.py`, `fallback.py` + `polygon.py` (C7 bar-count semantics) |
| New sections | `backend/apps/market/services/fed.py` (new), `backend/apps/snapshots/services/flowlite.py` (new — §6.2), `backend/apps/snapshots/services/__init__.py` (`_FETCHERS`), `backend/apps/snapshots/models.py` (`KIND_CHOICES` + migration), `token_budget.py` |
| Form 4 | `backend/apps/market/services/edgar.py` call site in the filings fetcher, `backend/apps/secrets/data_sources.py` (label already claims it) |
| Events seed | `backend/apps/market/services/events_seed.py`, `serializer.py` (`_render_events`) |
| Post-TV | `backend/apps/market/services/tradingview.py` (`INDEX_SYMBOLS`/`FUTURE_SYMBOLS`), `symbols.py` (`$DXY` alias), `vix.py`, `yields.py` (per-tenor divisor) |

No new Python/JS dependencies, no new compose services, no new Celery tasks, no new
feature flags (`feature_flags.py` untouched; `scheduled_tasks.py` untouched).

## 3. Workstream A — Delivery: defaults and the UI ceiling

### A1. DEFAULT_INCLUDES
`TradingProfile.DEFAULT_INCLUDES` becomes
`["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"]`.
`fundamentals`, `filings`, `treasury`, `overnight`, `image`, `notes`, `fed`, `flowlite`
stay opt-in. `vix` remains force-appended by `capture_for_existing`, never listed.

**Landmine (from CLAUDE.md):** `TradingProfile.save()` seeds `default_includes` only when it
is *empty* — the constant change alone reaches no existing profile. A data migration
appends the five new kinds to every existing profile's `default_includes` (idempotent:
append-if-missing, preserve order and any user-added kinds; reverse = no-op). Migration
reviewed by the `migration-reviewer` agent.

**Keyless-chain caveat (accepted):** with neither Schwab nor Tradier configured, the chain
fetcher raises and every default capture carries a `failed` chain section rendered
`_(unavailable: …)_`. That is the honest behavior; the snapshot still goes `ready` off the
other sections. No suppression logic.

### A2. Frontend include ceilings
Three UI surfaces currently make "opt-in" unreachable; all three open up:

- `frontend/src/pages/profiles/types.ts` `SECTION_OPTIONS` grows from 5 kinds to the full
  user-selectable list (everything in `_FETCHERS` except `vix`, which is always-on and
  shown as a non-toggleable "always included" chip in `ProfileForm`).
- `SchedulesPage.tsx` gains a section-includes editor bound to
  `ObserverSchedule.default_includes` (the API field already exists —
  `frontend/src/api/observer.ts` — the page just never sets it). Empty = inherit profile.
- `SnapshotSectionPicker.tsx` (manual composer) adds its missing kinds
  (`overnight`, `fundamentals`, plus the new `fed`/`flowlite`).

No backend API changes; `schema.yml`/`schema.d.ts` regenerate only for the new
`SnapshotSection.kind` choices (§6).

## 4. Workstream B — Render the computed-but-discarded

All changes in `serializer.py` render functions plus two small payload/service changes.
None add an external fetch.

- **B1 Sector table.** `context._fetch` keeps each sector ETF's `pct_change` alongside
  `last` (both already in the single batched `fetch_quotes` result — today the pct_change
  is discarded). `_render_breadth` replaces the leader/laggard-only line with a compact
  11-row table `Sector | 1d% | 5d% | RS vs SPX (5d)` joining quote pct_change with the
  full `sector_rotation` rows already computed in the payload.
- **B2 GEX by strike.** `option_analytics._gex` already builds a per-strike GEX dict and
  throws it away, returning only total + flip strike. Return the top ±3 strikes by absolute
  GEX and render one "GEX by strike" line in the chain analytics block (gamma walls/magnets
  become visible).
- **B3 Positioning concentration.** The chain render's strike table keeps its current
  columns; a new summary line per side lists the top-5 strikes by OI and by volume
  (data already in the persisted payload) so the AI can see *where* positioning
  concentrates without doubling table rows.
- **B4 Unusual activity in the chain section.** `_render_chain` calls
  `apps.analytics.services.unusual_options.unusual_options(ticker=…, at=captured_at)`
  (keyword-only signature) against the just-persisted `OptionChainSnapshot` (pure DB read)
  and renders the top flagged lines with their reasons as an "Unusual activity" list.
  Renderers currently receive only the section payload, so `captured_at` is plumbed through
  `_render_section` (or read off the snapshot passed to `serialize_for_ai`). This adds a
  `snapshots → analytics` import — no import-linter contract forbids it and no cycle results
  (analytics imports `market.models` only). Degrades to nothing on no rows.
- **B5 Events detail.** `_render_events` renders `forecast`/`prior`/`actual` from
  `detail` when non-None (macro rows) and `eps_actual`/`rev_est` (earnings rows) — all
  captured today, all dropped at render.
- **B6 Filings + treasury renderers.** Both sections currently ship as raw ` ```json `
  dict dumps (no `_RENDERERS` entry). Filings gets a `Form | Filed | Title | URL` table
  (with the Form 4 subsection from §6.3); treasury gets a two-line rates/debt summary.

## 5. Workstream C — New data through existing paths

- **C1 Credit spreads (closes a "missing").** Add `"BAMLH0A0HYM2": "HY OAS"` and
  `"BAMLC0A0CM": "IG OAS"` to the FRED `SERIES` dict. `fetch_macro` iterates `SERIES`
  generically and `_render_macro` iterates `series.values()` generically, so the two rows
  flow to the prompt with zero further code. Same free key, same 6h cache, same lag note.
  Optional live proxy: `HYG`/`LQD` quotes join `CONTEXT_SYMBOLS` (plain ETFs — free-provider
  quotable) with one render line.
- **C2 VVIX.** `vix_term_structure` extends its one batched call to
  `fetch_quotes(["$VIX", "$VVIX", "/VX", front, second])`, adds a
  `vvix {symbol,last,pct_change} | None` payload key and a `vvix_vix_ratio` when both quote.
  The section's raise condition is unchanged — a missing VVIX can never fail the section.
  `_render_vix` adds one line; the no-Schwab note extends to mention VVIX. (Schwab-less
  VVIX arrives via §7.)
- **C3 Dollar.** Wire `context.py`'s `MACRO` dict into the live quote fetch — it is *not*
  dead code (its values already feed the `ingest_daily_bars` universe, so UUP daily bars
  exist), but it is never quoted into the context payload. Add `UUP` to `CONTEXT_SYMBOLS`,
  a `dollar` payload key in `_fetch`, and one `_render_breadth` line. UUP is a plain ETF,
  so it degrades gracefully through every fallback provider. FRED `DTWEXBGS` stays in macro
  as the official (lagged) series; the true live DXY arrives via §7.
- **C4 Index complex in breadth.** `CONTEXT_SYMBOLS` gains `SPY`, `/ES`, `/NQ`
  (alongside the existing `$SPX`/`QQQ`), rendered as an index row set with last + %chg.
  **Fallback robustness (skeptic-verified):** Alpaca's quote fetch is one whole-batch
  request that returns `{}` for the entire batch if any symbol is rejected — on the fallback
  path, futures/index symbols are fetched in a *separate* `fetch_quotes` call from the
  equity/ETF symbols so a rejected `/ES` cannot blank SPY/QQQ. (Post-TV this matters less —
  TradingView is first and maps futures — but the split protects the TV-disconnected path.)
- **C5 Factor returns (closes a "missing").** `FACTOR_ETFS = ["MTUM","VLUE","QUAL","USMV","IWM","SPY"]`
  beside `SECTOR_ETFS`; add `*FACTOR_ETFS` to the `ingest_daily_bars` universe (one line);
  compute per-ETF 1/5/20-session returns via the existing `intel.return_over_sessions`
  plus three derived spreads — momentum−value (`MTUM−VLUE`), size (`IWM−SPY`),
  growth-vs-value proxy (`QQQ−SPY`, QQQ bars already ingested). Attach as
  `payload["factor_returns"]` (best-effort, `[]` on thin data like `sector_rotation`) with
  a compact render block in breadth. Empty on a cold install until the beat has run.
- **C6 Computed breadth metrics.** Add to `intel.py` off stored daily bars:
  `pct_above_sma(period)` for 20/50 over `SECTOR_ETFS` + watchlist, and high/low counts —
  **labeled by their real window** ("60-session high", not "52-week") until C7's deeper
  ingest accumulates; honest `None`/`[]` when bars are thin. Render as one internals line.
  Additionally, try-and-see Schwab symbols `$UVOL`/`$DVOL` in the `BREADTH` batch
  (`context.py` already documents that Schwab may or may not return `$`-breadth indices;
  absent rows silently omit, warm-up gate extended to them).
- **C7 History depth.** `ingest_daily_bars` fetches 260 daily bars (~52 weeks) instead of 60
  for its fixed universe (sector/factor ETFs + $SPX + QQQ + MACRO values; watchlist tickers
  too). Two constraints the naive "one knob" version misses:
  - **Retention.** `OHLCBar` is *not* unbounded — `core.prune_retention` deletes bars older
    than `AI_RETENTION_OHLC_DAYS` (default 400 calendar days ≈ 275 trading bars, just
    covering 52 weeks). The 52-week metrics (C6, C8) therefore document a floor: keep
    `retention_ohlc_days ≥ 380`, enforced softly by clamping the metrics' window to the
    retained depth and labeling honestly (C6's real-window labels already do this).
  - **Fallback bar-count semantics.** The 260-bar knob is real on Schwab (fetch-then-`[-bars:]`),
    Alpaca, and Twelve Data (true bar counts) — but `alt_bars` passes the count to
    Tiingo/Polygon as a *calendar-day lookback* (260 days ≈ 178 bars), and `polygon.py`
    hardcodes an aggregates `limit: 120`. Fix in the same change: convert `days ≈ bars × 1.45`
    for those two in `alt_bars` and raise Polygon's hardcoded limit.

  After one nightly run this makes C6's high/low counts and C8's summary real 52-week metrics.
- **C8 Long-horizon ohlc summary.** `_render_ohlc` appends a computed block for the primary
  ticker from stored `OHLCBar` + `returns.py`/`intel.py` helpers: 52-week high/low and
  %-off-high, distance from SMA 20/50/200, and 5/20/60-session returns. No new fetch;
  derives from whatever bars exist (honest omission when thin). This surfaces the persisted
  bar archive the audit found "never reaches the prompt".
- **C9 Live curve read in macro.** `_render_macro` adds a computed live long−short proxy
  spread from `live_yields` (e.g. `$TYX − $IRX`, labeled a proxy) and labels the FRED
  `T10Y2Y` row as the official 2s10s. A true live 2s10s needs a 2Y quote, which **no
  Schwab-served symbol provides** — it arrives only via §7's TradingView tenor rows, and on
  a Schwab-connected install only if the optional TV-direct consult (§7, E-optional) is built.
- **C10 Events seed refresh.** Extend `events_seed.py` with 2027 dates and add PCE + GDP
  rows (`_MACRO_MAP` already carries their match needles, so they flow through
  `_upsert_macro` unchanged). Post-TV this seed is fallback-only, but it must not lapse
  on 2026-12-10 for TV-disconnected installs.
- **C11 Dividends & splits into events.** `CorporateAction` rows (splits + dividends,
  refreshed nightly by `market.refresh_corporate_actions`) never reach any prompt today —
  they only feed `returns.py` split adjustment. The events section render adds upcoming
  ex-dividend/split rows for watchlist tickers (pure DB read on already-refreshed data);
  `_render_events` gets a short "Corporate actions" block. Degrades to nothing when empty.

## 6. Workstream D — New sections

Both new kinds follow the full section gate stack: `_FETCHERS` entry, `KIND_CHOICES`
(strings ≤16 chars: `fed` = 3, `flowlite` = 8) + migration, `_title` + `_RENDERERS`
entries, FE include lists (§A2), schema regen. Both are **prunable**, inserted after
`news` in `_PRUNE_ORDER` (`chain→ohlc→news→fed→flowlite→breadth→quotes→positions`) —
unlike `vix`/`macro` they are enrichment, not core context.

### 6.1 `fed` — Fed communication (closes a "missing")
`backend/apps/market/services/fed.py`, keyless, mirroring the `edgar.py`/`treasury.py`
pattern: fetch the Federal Reserve's public RSS feeds — monetary-policy press releases
(`https://www.federalreserve.gov/feeds/press_monetary.xml`) and speeches + testimony
feeds — with `requests` (the actual edgar/treasury/fred pattern; `httpx` is a
secrets-app dependency only), a descriptive User-Agent (the EDGAR precedent), and
`cache.get_or_fetch` under a new `fed` TTL (3600s) in `apps/market/cache.py`.
Parse titles/dates/links/description snippets with stdlib `xml.etree.ElementTree`. This is
the backend's first XML parse, and **two** gates fire on it: ruff S314 (`# noqa: S314`) and
the *blocking* `semgrep ci` registry packs' use-defusedxml/XXE rules — silence the latter
with the repo's existing convention, an inline `# nosemgrep: <full-rule-id> -- <reason>`
(precedent at `market/tasks.py:65`), the exact rule id confirmed by running the packs
against the new file at implementation time. Shared justification: response size capped at
512 KB before parsing, and modern-stdlib ElementTree does not resolve external entities
(the rules target XXE).
Return `[]` on any failure — never raises (the `treasury.py` contract). Exact feed URLs are
verified at implementation time (they are stable, published Fed endpoints, but confirm
before hardcoding). Renderer: `## Fed communication` — dated items from the last 14 days,
newest first, capped at 10, plus a "next FOMC in Nd" line read from `MarketEvent`
(kind `fomc`) so decision proximity is visible even when the feeds are quiet.
`MOCK_EXTERNAL`: `is_mock_mode()` short-circuit returning two canned items, so the e2e
stack renders the section without network.

### 6.2 `flowlite` — volume-based flow proxy (the honest answer to "flows")
Real fund/ETF flow data has no free programmatic source (audit-verified). `flowlite`
computes a *flow-pressure proxy* from data already in the repo — and says so in its render
header ("volume-based proxy — not fund-flow data"):

- volume z-score vs the trailing 20-session average for `SPY`, `QQQ`, and the 11 sector
  ETFs, off stored `OHLCBar` daily rows (populated nightly by `ingest_daily_bars`);
- put/call volume-ratio delta vs the snapshot's *prior* `OptionChainSnapshot` for the
  primary ticker (pure DB read);
- the top unusual-options lines (shared service with B4).

Service lives in `apps/snapshots/services/flowlite.py` — deliberately *not* under
`apps/market`, because the P/C-delta and unusual-lines inputs import
`apps.analytics.services.unusual_options`, and a `market → analytics` import would invert
the existing `analytics → market.models` direction (no CI contract forbids it, but the
one-way dependency is worth keeping). From `apps/snapshots` the import is the same one B4
already introduces. Zero external fetches; degrades to an empty section until bars exist.
Form 4 insider prints (§6.3) intentionally stay in `filings` — they are documents, not
tape pressure.

### 6.3 Form 4 into `filings`
The filings fetcher makes a **separate** `fetch_filings(…, forms=("4",), limit=5)` call and
merges the result — *not* an addition to the existing forms tuple: `fetch_filings` applies
one shared newest-first `limit` across all matched forms, and Form 4s print frequently
enough that a shared budget would evict the 10-K/10-Q/8-K rows the section shows today.
(The `forms` parameter is already plumbed through `edgar.py`; the audit found the
capability advertised in `data_sources.py` but never fetched.) The B6 filings renderer
shows the Form 4 rows as a separate "Insider activity (Form 4)" subsection.
`is_equity_like` gating unchanged. This also retires the doc-vs-code drift: the
`data_sources.py` blurb becomes true.

## 7. Workstream E — Post-TradingView tasks (gated on that branch merging)

Extend the symbol map in `backend/apps/market/services/tradingview.py` — `$`-prefixed rows
go in `INDEX_SYMBOLS`, `/`-prefixed in `FUTURE_SYMBOLS` (the two dicts `to_tv_symbol`
dispatches on). Each row is live-verified by quoting the symbol through
`tv_get_symbol_data_batch` once connected — extending the TV spec's §9 checklist, which
verifies tool shapes but has no symbol step of its own:

| App symbol | TradingView symbol | Quote unit | What it repairs |
|---|---|---|---|
| `$VVIX` | `TVC:VVIX` | index level | C2's VVIX **without Schwab** |
| `$DXY` (new alias in `symbols.INDEX_ALIASES`) | `TVC:DXY` | index level | true live ICE DXY — quoted into the C3 dollar line when available, superseding UUP as the preferred value |
| `$IRX` / `$FVX` / `$TYX` | `TVC:US03MY` / `TVC:US05Y` / `TVC:US30Y` | **percent** (see below) | **Schwab-less** live yields beyond `$TNX` |
| `$US2Y` (new) | `TVC:US02Y` | **percent** (see below) | a live 2Y — **Schwab-less installs only** by default (see scoping note) |
| `$SKEW` | `CBOE:SKEW` | index level | optional extra vol-complex line in the vix section |
| `/ZQ` | `CBOT:ZQ1!` | price | deferred hook for a market-implied Fed-path read (not rendered in this spec) |

**Unit contract (blocker found in review):** `yields.py` divides every quote by 10 because
CBOE `$`-yield-indices quote yield×10 — but TradingView's `US02Y/US03MY/US05Y/US30Y`
publish the yield **in percent** (US10Y ≈ 4.1, not 41). A flat ÷10 would silently render
those tenors 10× too low (positive numerics pass the `last > 0` gate). `YIELD_INDICES`
therefore becomes `ticker → (tenor, divisor)` — 10 for the CBOE `$`-indices, 1 for
percent-quoted TV tenors — and the unit is part of each row's live verification.

**Scoping note ($US2Y and C9's live 2s10s):** the fallback chain engages only on
`SchwabNotConnectedError`, and the locked TV rule is "the first configured provider
answers, even if it answers empty". Schwab serves no 2Y yield index, so on a
Schwab-connected install `$US2Y` never quotes and the 2Y tenor slot still doesn't render.
The row as specced repairs **TV-connected, Schwab-disconnected** installs. *Optional
E-item* (the one deliberate per-symbol provider merge in this spec): `live_yields` consults
the TradingView provider directly for tenors Schwab cannot serve (`$US2Y` only), gated on
`tradingview.is_connected()` — build it only if the live 2s10s matters on Schwab-connected
installs.

Also post-TV, optional: `vix.py` learns a continuous-second-month fallback — when the dated
`/VX` legs are unusable but continuous quotes exist, try `CFE:VX2!` (via a `/VX2` mapping)
for the second leg so the Schwab-less contango read survives (today the TV fallback yields
spot + continuous front only). Exact TV symbol spellings above are live-verified; any that
do not resolve are dropped (map rows degrade to `None` → absent, never failing sections).

**Analyst revisions**: deliberately *not* a snapshot section in this spec. Post-TV the
`tv_get_forecasts` / `tv_get_technicals_rating` tools cover it on demand across all three
providers. A snapshot-side "Rec trend" line in `fundamentals` via the TV normalizer is a
possible follow-up once the TV integration has baked.

## 8. What this spec deliberately does not fix (audit items, dispositioned)

- **Breadth internals without Schwab** — `$ADVN`/`$DECN`/`$TICK`/`$TRIN` map to `None` on
  TradingView and no free provider quotes them; C6's computed metrics are the mitigation.
- **Real per-ETF flows** — no free source; `flowlite` is the honest proxy. A paid flow API
  would be a new keyed provider following the `fred.py` pattern (out of scope).
- **Multi-underlying chains / index (SPX) gamma** — the chain section stays
  single-underlying; a SPY chain is the usable index proxy. Revisit after defaults bake.
- **Fed content summarization** — `fed` delivers headlines/links as data; interpreting
  statements is the AI's job at run time (or a tool call), not capture's.
- **The morning-briefing capture stays `['breadth']`** — deliberate: `assemble.py` carries
  its own deterministic events/news/theses/triggers/book sections outside the snapshot, so
  A1's richer profile defaults are intentionally not inherited there (a full default
  capture would double-deliver events/news and slow the daily run).
- **Marketaux per-ticker sentiment stays unstored** — it is fetched-and-dropped (the
  root-cause-2 pattern), but the news path is Finnhub-first, so Marketaux serves only
  Finnhub-unkeyed installs; persisting it needs a `NewsItem` column for a rarely-hit path.
  Accepted; revisit if the TV-first news fallback changes the traffic.
- **The news section's 24h lookback / 15-item cap stays** — `fetch_news` is already
  parameterized (the briefing passes its own values); the snapshot fetcher keeps the
  defaults. With news now default-on, the caps govern every capture — accepted as the
  token-sane default; per-schedule tuning is a follow-up once A2's includes editor exists.
- **Intraday OHLC stays single-primary** — by token design: `watchlist_daily` (plus C8's
  computed summary) is the cross-name answer; per-ticker intraday bars for the whole
  watchlist would dominate the payload for marginal signal.
- **Diff-mode observers** bypass `serialize_for_ai`, so none of the render work here is
  visible on that path (pre-existing; unchanged).
- **Image/citation payload bypasses** — chart-image base64 and Claude `search_result`
  blocks ride outside `prune_to_budget`'s accounting (pre-existing; unchanged).
- **The 40k unknown-model default budget** (`catalog.py` dataclass default, applied to any
  Local model not in the catalog) stays — the prune order handles it; raising it is a
  catalog decision out of scope here.

## 9. Token & cost math

Verified against `apps/ai/catalog.py`: Claude models carry 150k payload budgets,
gpt-5 300k, gpt-5-mini/nano 200k, unknown/Local 40k. Worst-case everything-on renders
≈25–40k tokens today; B/C additions are compact lines/tables (~1–2k) and `fed`/`flowlite`
~0.5–1k each — comfortably inside every catalog budget, binding only at the 40k Local
fallback, where the §6 prune order sheds `chain→ohlc→news→fed→flowlite` first.

**Recurring cost (corrected in review — the number the decision was taken on was 3–10×
low):** richer defaults multiply scheduled-fire input tokens. At the catalog's Opus input
price ($15/MTok), a ~30k-token prompt is ~$0.45/fire — an every-10-min schedule is
**≈$17.5/day input on a market-hours cron (39 fires) and ≈$65/day run 24/7 (144 fires)**,
before output tokens. Cheaper models change the slope, not the shape (gpt-5 ≈ 1/3 of that;
Haiku/mini far less). Mitigations that already exist: per-schedule `default_includes`
overrides (now editable in the UI, §A2 — the recommended fix for any hot schedule), diff
mode, batch mode (−50%), the observer response cache, coarser crons, and the cost caps.
One interaction to document in CLAUDE.md: live-quote lines in default sections make
byte-identical prompts rarer, reducing `OBSERVER_RESPONSE_CACHE_ENABLED` hits.

## 10. Testing

Per repo conventions (SDK-boundary mocks, no respx; `parametrize`-heavy):

- `profiles`: migration appends kinds idempotently, preserves user-added kinds; new-profile
  seeding; `SECTION_OPTIONS` parity test FE-side (vitest) against the kind list.
- `market/tests/test_context.py`: pct_change retained per sector; index-row split fetch on
  the fallback path (rejected futures symbol cannot blank the ETF batch); factor returns +
  spreads (thin-data `[]`); `$UVOL`/`$DVOL` absent-row tolerance; UUP dollar key.
- `market/tests/test_fred.py`: OAS rows flow through `fetch_macro` generically.
- `market/tests/test_vix.py`: VVIX in the batch, `vvix=None` never fails the section,
  ratio only when both quote, note text extension.
- `market/tests/test_fed.py`: feed parse (fixture XML), size cap, `[]` on error/HTTP
  failure, cache key, mock mode.
- `market/tests/test_flowlite.py` (or under snapshots): z-scores off seeded bars, P/C delta
  vs prior chain snapshot, empty on cold DB.
- `market/tests/test_edgar.py`: Form 4 fetched via its own call + limit; the base-forms
  call unchanged (an active-insider fixture proves 10-K/10-Q/8-K rows are not evicted).
- `market/tests/test_yields.py`: per-entry divisor — a CBOE ×10 row and a percent-quoted
  row render the same true yield (guards the §7 unit contract).
- `market/tests/test_fallback.py`: `alt_bars` converts bar counts to calendar days for
  Tiingo/Polygon (C7); Polygon limit covers ≥260 bars.
- `snapshots/tests`: serializer renders for B1–B6 + both new sections (golden-ish asserts on
  section text), prune order with `fed`/`flowlite` inserted, `KIND_CHOICES` migration,
  `capture` loop over the new kinds, MOCK_EXTERNAL e2e fixture coverage.
- `analytics`: unusual-options reuse from the chain render (query-count guard — one bounded
  DB read per render, `django_assert_max_num_queries`).
- Hypothesis: extend the token-budget property tests to the new prune order.
- E2E: the existing snapshot ui/api lanes pick up the new sections under `MOCK_EXTERNAL`
  (fixtures above); one composer test asserts the full section picker list.
- `make check-migrations`, schema regen (`make schema` + the copied-schema `gen:api`
  workaround), coverage floors unchanged.

## 11. Documentation in the same change

README + FEATURES capability bullets (new sections, credit spreads, VVIX, factor returns,
dollar line — extending the 2026-09-19 doc sync); CLAUDE.md capture-pipeline paragraph
(new kinds, new prune order, new defaults + the data-migration landmine, the response-cache
interaction); `docs/marketing-copy.md` Show HN bullet if it lists sections;
`apps/secrets/data_sources.py` EDGAR blurb becomes true via §6.3 (verify wording).

## 12. Out of scope

Real fund-flow providers, analyst-revision snapshot rendering (post-TV follow-up), `/ZQ`
rendering, VIX-options skew, multi-underlying chains, auth, observer diff-mode payload
unification, image/citation token accounting, catalog budget changes, any TradingView
client work (owned by `worktree-tradingview-mcp`).
