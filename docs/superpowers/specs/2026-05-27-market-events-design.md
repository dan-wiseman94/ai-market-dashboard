# Market events (earnings + curated macro) — design

**Date:** 2026-05-27
**Status:** Approved (pending spec review)
**Topic:** A forward-looking `MarketEvent` store (per-ticker earnings dates + a curated US-macro set) that enriches snapshots, powers an earnings-aware trigger leaf, and surfaces on a new `/events` page — the foundation the Morning Briefing will build on.

## Problem

The dashboard captures rich *present-tense* market state (quotes, OHLC, chains, news, breadth) but has **no notion of the calendar of scheduled catalysts**. A trader's most basic context — "NVDA reports in 2 days," "CPI drops Thursday," "FOMC next week" — is absent everywhere:

- The AI payload (`serialize_for_ai`) can't tell the model an earnings print is imminent, so observations are blind to the single biggest near-term risk on a name.
- Triggers can alert on price/volume/VIX/P&L but **not** on proximity to a scheduled event.
- There's no surface that answers "what's coming up this week across my watchlists?"

This is the first of a four-feature roadmap (decided during brainstorming): **Events calendar → Morning Briefing → AI calibration scorecard → Semantic recall.** Events is sequenced first because it's the cheap *unlock*: the Briefing wants "upcoming earnings/FOMC/CPI" as an input, and triggers want a `days_to_earnings` leaf. Building it now means the Briefing ships earnings-aware with no retrofit.

Note on naming: `apps.market.calendar` already exists and means the **trading-session** calendar (market open / half-day / per-symbol overrides). This feature is deliberately **"market events"** — a sibling to `NewsItem` — not a second "calendar."

## Non-goals (YAGNI)

- **Corporate actions** (ex-dividend dates, splits). Different cadence and source shape; add later if the Briefing wants them.
- **Non-US macro.** The economic firehose is global; we filter hard to a curated US high-impact set.
- **Intraday econ "surprise" triggers** (actual-vs-forecast beats). The store holds the *schedule*; reacting to the *print* is a future leaf.
- **A generalized `days_to_<event>` trigger leaf.** v1 ships only `days_to_earnings` (per-ticker). Countdown-to-macro is future.
- **Earnings-whisper numbers, multi-source reconciliation, historical backfill** beyond the forward window.
- **Push streaming / real-time event revisions.** A daily refresh is sufficient — scheduled-event dates do not move intraday.
- **Editing `apps/market/services/context.py` or `MarketContextStrip.tsx`.** Both are mid-edit in the working tree; the dashboard badge is delivered as its own component to avoid collision.

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Event scope | Earnings + curated US macro (FOMC, CPI, NFP, PCE, GDP) | Richest input for the Briefing; macro filtered to a tiny high-impact allow-list |
| Domain placement | Extend `apps.market` (not a new app) | Quotes/OHLC/chain/news all live here; events *are* market data |
| Model shape | One polymorphic `MarketEvent` table (`kind` + nullable `ticker` + `detail` JSON) | "Next N upcoming events" is one ordered query that the page, badge, Briefing, and trigger leaf all share; JSON absorbs per-type field differences (as `OptionChainSnapshot.payload` / `NewsItem` already do) |
| Macro data source | Finnhub `/calendar/economic`, filtered to US + high-impact + name allow-list | Reuses the existing Finnhub credential/client/cache from `news.py` |
| Macro fallback | A shipped `SEED_MACRO_EVENTS` list (`source="seed"`), used only when the econ endpoint is empty/errors | Macro still works if `/calendar/economic` isn't on the user's Finnhub plan; live pull upserts over it |
| `days_to_earnings` ops | Comparison ops only (`<,<=,==,>,>=`), no crossing | A daily integer countdown has no meaningful "crossing"; the trigger cooldown handles repeat-firing |
| AI enrichment seam | New **opt-in `"events"` snapshot section** (not forced into defaults) | Mirrors every other section; per-capture opt-in; back-compat for existing profiles |
| Dashboard surface | Standalone `<UpcomingEvents>` component on the Dashboard | Avoids the in-flight `context.py` / `MarketContextStrip` edits |
| UI reach | Full: store + refresh + trigger leaf + AI section + dashboard badge + dedicated `/events` page | Chosen during brainstorming over backend-only / lean variants |

## Architecture

Six seams, each matching an existing pattern. No new app, no new credential, no new service container.

```
Finnhub /calendar/earnings ─┐
Finnhub /calendar/economic ─┤   apps/market/services/events.py        (clone of news.py)
SEED_MACRO_EVENTS (fallback)┘            │  fetch + filter + upsert + cache + MOCK_EXTERNAL
                                         ▼
                                   MarketEvent  (apps/market/models.py)
                                         │
        ┌────────────────────────────────┼───────────────────────────────────┐
        ▼                                 ▼                                    ▼
 market.refresh_events            days_to_earnings leaf              "events" snapshot section
 (beat, daily)                    (triggers/dsl + metrics)           (capture _FETCHERS + serializer _RENDERERS)
        │                                 │                                    │
        ▼                                 ▼                                    ▼
   keeps store fresh            evaluator (pure, unchanged)         reaches the AI payload
                                                                              │
   GET /api/market/events/  ◀──────────────────────────────────────── EventsPage + <UpcomingEvents> badge
```

### 1. Data model — `apps/market/models.py`

One table, modeled on `NewsItem`'s `(source, external_id)` dedup + multi-index conventions:

```python
class MarketEvent(models.Model):
    KINDS: ClassVar = [("earnings","earnings"),("fomc","fomc"),("cpi","cpi"),
                       ("nfp","nfp"),("pce","pce"),("gdp","gdp")]
    source       = models.CharField(max_length=16)                 # "finnhub" | "seed"
    external_id  = models.CharField(max_length=80, db_index=True)  # "EARN:NVDA:2026-05-28" | "CPI:2026-06-11"
    kind         = models.CharField(max_length=16, choices=KINDS)
    ticker       = models.CharField(max_length=16, blank=True, default="", db_index=True)  # "" for macro
    title        = models.CharField(max_length=200)                # "NVDA earnings (AMC)" / "CPI (May)"
    event_time   = models.DateTimeField(db_index=True)
    when_hint    = models.CharField(max_length=8, blank=True, default="")  # bmo|amc|"" (earnings session)
    impact       = models.CharField(max_length=8, blank=True, default="")  # high|medium|low (macro)
    detail       = models.JSONField(default=dict)                  # eps_est/eps_actual/rev_est | forecast/prior/actual
    fetched_at   = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["source","external_id"], name="uniq_event_source_id"),
        ]
        indexes: ClassVar = [
            models.Index(fields=["ticker","event_time"]),
            models.Index(fields=["kind","event_time"]),
            models.Index(fields=["event_time"]),   # global upcoming timeline
        ]
```

`external_id` convention: earnings `f"EARN:{symbol}:{date}"`, macro `f"{KIND}:{date}"`. A moved earnings date produces a new row; the prior ages out via the refresh prune. Migration: `apps/market/migrations/0006_marketevent.py` (plain `CreateModel`, fully reversible).

### 2. Data source & service — `apps/market/services/events.py`

A near-clone of `apps/market/services/news.py`, reusing `_finnhub_api_key()`, the `_finnhub_get(path, params, key)` shape, the `is_mock_mode()` short-circuit, `cache.get_or_fetch`, and `update_or_create` upsert.

- **`fetch_earnings(tickers, *, ahead_days=30) -> list[dict]`** — Finnhub `/calendar/earnings?from&to&symbol=T` per ticker (cached per `(ticker, window)`). Maps each row → `kind="earnings"`, `when_hint` from Finnhub's `hour` field (`bmo`→before-open, `amc`→after-close), `detail={eps_est, eps_actual, rev_est}`. Upserts.
- **`fetch_macro(*, ahead_days=45) -> list[dict]`** — Finnhub `/calendar/economic?from&to` (one cached call), filtered by `country == "US"` AND `impact == "high"` AND an event-name allow-list mapped to our `kind` (`FOMC` rate decision, `CPI`, `Nonfarm Payrolls`→`nfp`, `Core PCE`→`pce`, `GDP`). On empty/error → `SEED_MACRO_EVENTS`. Upserts with `source` set accordingly.
- **`upcoming_events(tickers, *, within_days, include_macro) -> dict`** — the **read** helper used by the API, the snapshot section, and the badge. Reads the store (`event_time__gte=now`, ordered), does a best-effort on-demand `fetch_earnings([t])` for any ticker with no stored earnings (mirrors news fetching live for ad-hoc tickers), returns `{"earnings":[…], "macro":[…]}`.
- **`SEED_MACRO_EVENTS`** lives in `apps/market/services/events_seed.py` — a small hand-maintained list of known upcoming high-impact US dates, sourced from the official Fed FOMC calendar + BLS/BEA release schedules. Explicitly best-effort; the live Finnhub pull upserts over it. The implementer populates it from the published calendars at build time (no dates are invented in this spec).
- **`_canned_events()`** — deterministic `MOCK_EXTERNAL` fixtures (one near-future NVDA earnings + one CPI), mirroring `_canned_news_items()`.
- **Cache:** add `"events": 3600` to `cache._TTL` (event dates are stable within a day).

### 3. Refresh task & beat — `apps/market/tasks.py` + `config/celery.py`

```python
@shared_task(name="market.refresh_events")
def refresh_events() -> dict:
    tickers = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    n_earn = len(events.fetch_earnings(tickers))
    n_macro = len(events.fetch_macro())
    pruned, _ = MarketEvent.objects.filter(event_time__lt=now() - timedelta(days=30)).delete()
    return {"earnings": n_earn, "macro": n_macro, "pruned": pruned}
```

Idempotent (upsert), safe to overlap. Beat entry in `config/celery.py`:

```python
"refresh-market-events-daily": {"task": "market.refresh_events", "schedule": crontab(hour=9, minute=0)},
```

`apps.market` is already in the explicit `autodiscover_tasks([...])` list, so the task registers without touching that list. **Ops:** beat does not hot-reload schedules on a running stack — the plan must call out `docker compose restart worker beat` after adding the entry (per CLAUDE.md).

### 4. Earnings-aware trigger leaf — `apps/triggers/`

- **`dsl.py`:** add `"days_to_earnings"` to `VALID_METRICS` and `TICKER_REQUIRED`. It needs a ticker, takes no window, and accepts only comparison ops. Validation already rejects unknown leaf keys and enforces ticker-required, so the only additions are set memberships (and a guard rejecting crossing ops for this metric, with a clear path-prefixed message).
- **`metrics.py` `build_snapshot`:** collect every `days_to_earnings` leaf's ticker, run **one** batched query for the next earnings per ticker (`MarketEvent.objects.filter(kind="earnings", ticker__in=…, event_time__gte=now).order_by("ticker","event_time")`), and set `snapshot[key] = (next_date − today).days`. **Unknown ticker → `None` → non-match**, consistent with every other metric. No Redis state (DB-backed, indexed, negligible per-tick cost).
- **`evaluator.py`:** pure comparison logic — **no change**.
- **Backtest** (`backtest.py`): `days_to_earnings` is a live/forward metric; like `vix`/`position_*` it is silently absent from per-bar historical snapshots (documented behavior — backtest evaluates only `price`/`pct_change`).
- **`describe.py`:** add a human phrasing ("NVDA earnings within 2 days").

### 5. AI enrichment — opt-in `"events"` snapshot section

- **`apps/snapshots/services/__init__.py`:** add to `_FETCHERS`:
  ```python
  "events": lambda *, watchlist_tickers, **_: {
      "data": events.upcoming_events(list(watchlist_tickers), within_days=14, include_macro=True)
  },
  ```
- **`apps/snapshots/serializer.py`:** add `_RENDERERS["events"]` (compact markdown — e.g. `## Upcoming events\n- NVDA earnings in 2d (AMC, est EPS 0.84)\n- FOMC in 5d (high)`) and an `"events": "Upcoming events"` entry in `_title`.
- **Defaults unchanged.** `events` is opt-in via a snapshot's `includes`, exposed in `SnapshotSectionPicker`. Existing profiles' `default_includes` are untouched (back-compat). Partial-failure handling is automatic (the capture loop marks a failed fetcher `failed`; the serializer already renders `_(unavailable: …)`).

### 6. API & frontend

- **API** — `GET /api/market/events/?tickers=NVDA,AMD&kind=earnings&within_days=14&include_macro=true`. New `MarketEventSerializer` + a function view/ViewSet in `apps/market/{serializers,views}.py`, route added to `apps/market/urls.py`. It sits under the existing `/api/market/` include, so the URL-ordering convention is not at risk. Read-only.
- **`/events` page** — `frontend/src/pages/EventsPage.tsx`: upcoming earnings grouped by date across watchlists + a macro timeline; built from `Skeleton`/`EmptyState`. Wiring: route in `router.tsx` (`{ path: "events", element: <EventsPage/>, handle: { crumb: "Events" } }`), a SideNav entry, a `go-events` command in `useDefaultCommands`, and the `g e` keyboard shortcut (verified free against the existing `g <x>` set).
- **Dashboard badge** — `frontend/src/components/UpcomingEvents.tsx`: a compact "next 2 events" chip strip rendered on `Dashboard.tsx`, fed by the same hook. Standalone (does not touch `MarketContextStrip`/`context.py`).
- **Client** — add `fetchUpcomingEvents` to `frontend/src/api/market.ts` and a `useUpcomingEvents` TanStack Query hook. Frontend TS interface uses the serializer's field names verbatim (incl. any `*_id` keys), per the DRF↔TS convention.

## Testing

Mirrors the existing market/triggers layout; `pytest.mark.parametrize` where it fits.

- **Service** (`apps/market/tests/test_events_service.py`): Finnhub earnings parse + per-ticker dedup; macro US/high-impact/allow-list filter; `MOCK_EXTERNAL` canned items; seed fallback when econ endpoint empty/errors; `respx` at the SDK boundary.
- **Model** (`test_events_model.py`): `(source, external_id)` uniqueness; ordering by `event_time`.
- **DSL** (`apps/triggers/tests/…`): `days_to_earnings` accepted; window rejected; crossing op rejected; ticker required.
- **Metrics** (`…`): days computed from a seeded `MarketEvent`; `None` when no upcoming earnings; batched-query correctness across multiple tickers.
- **Serializer** (`apps/snapshots/tests/test_serializer.py`): `events` renderer output; `unavailable` path when the section failed.
- **API contract** (`apps/market/tests/test_events_endpoint.py`): filter params, ordering, macro toggle.
- **Frontend** (`vitest`): `useUpcomingEvents` hook + `EventsPage`/`UpcomingEvents` render (loading/empty/populated), using the existing `mockApi` helpers.

## Ops & migration notes

- One migration: `apps/market/migrations/0006_marketevent.py` (`CreateModel`, reversible).
- After adding the beat entry: **`docker compose restart worker beat`** (beat won't pick up a new schedule on a running stack; `apps.market` is already autodiscovered, so no celery-list edit is needed).
- No new credential or env var. Requires the existing Finnhub `ApiCredential`; without it, earnings return empty and macro falls back to `SEED_MACRO_EVENTS` (both degrade quietly, like `fetch_news`).

## Implementation order (for the plan)

1. Model + migration + cache TTL.
2. `events.py` service (+ `events_seed.py`, `_canned_events`) with tests.
3. `market.refresh_events` task + beat entry.
4. `days_to_earnings` DSL + metrics + describe, with tests.
5. `"events"` snapshot section (fetcher + renderer + title) with tests.
6. `GET /api/market/events/` endpoint + serializer with contract test.
7. Frontend: client + hook, `EventsPage`, `<UpcomingEvents>` badge, route/nav/command/shortcut, with vitest coverage.

Each step is independently testable; steps 4–7 depend only on steps 1–2.
