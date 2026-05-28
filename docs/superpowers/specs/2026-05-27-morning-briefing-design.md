# Morning Briefing (`apps.briefing`) — design

**Date:** 2026-05-27
**Status:** Approved (pending spec review)
**Topic:** A daily hybrid briefing — deterministic data sections (open theses status, upcoming events, overnight trigger firings, overnight news, a fresh market snapshot) + a best-effort AI "what matters today" synthesis — on a `/briefing` page + a notification. Feature #2 of the four-feature roadmap; consumes the `MarketEvent` store from feature #1.

## Problem

The dashboard has rich per-surface views (theses, triggers, observer timeline, events) but **no single place that answers "what do I need to know this morning?"** A daily-use trader has to manually check: which open theses are near their target/invalidation, what earnings/macro events land this week, which triggers fired overnight, what news broke on the watchlists, and where the market is opening. That synthesis is exactly what an AI cockpit should do for you — and it's the highest daily-use magnet of the roadmap.

This is feature #2 (sequenced after the events calendar precisely so the briefing ships earnings/macro-aware). It composes subsystems that already exist — `apps.thesis`, `apps.triggers` firings, `apps.market` news + the new `MarketEvent` store, `apps.snapshots` capture — and the observer's AI-fire plumbing (`run_ai_on_message`, `notify`, beat scheduling).

## Non-goals (YAGNI)

- **Per-profile briefings.** A single global daily briefing (single-user app). The config picks one profile only as the AI *voice/provider*.
- **Email / external delivery.** In-app notification + page only. Off-device delivery is the deferred `NotificationSink` work.
- **Structured / typed-card AI output.** We chose the hybrid: deterministic data sections (typed, code-assembled) + a freeform streamed AI synthesis. No `BriefingReport` Pydantic schema.
- **Configurable section ordering / custom user sections.** Fixed section set.
- **Briefing analytics / historical trends.** `BriefingRun` rows persist for history, but no aggregation surface.
- **Editing the observer or events subsystems.** The briefing only *reads* their outputs and reuses their helpers.

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Composition | Hybrid: deterministic data sections + best-effort AI synthesis | Renders fully with no AI key; AI comments rather than regurgitates; mirrors the `PostMortem` deterministic-verdict + best-effort-narrative pattern |
| Scope | Full + fresh snapshot | Theses + events + overnight triggers + overnight news + a freshly captured market-context snapshot (persisted, `snapshot_ref`'d) |
| Home | New `apps.briefing` app | Cross-cutting daily synthesis — not market data, not an observer fire; warrants its own boundary |
| Config | `BriefingConfig` singleton | Single-user; one global briefing. Holds enable + send-at + AI-voice profile + lookback knobs |
| Storage | `BriefingRun` model (own model, like `PostMortem`) | Deterministic sections queryable in `data` JSON; FK to the snapshot + to the AI `Message`; status/history |
| AI synthesis transport | Synthetic user `Message` in a dedicated briefing thread → `run_ai_on_message` | Reuses the streaming + cost-tracking pipeline verbatim; provider-agnostic; visible history |
| Once-per-day idempotency | Unique `scheduled_date` claim on `BriefingRun` (scheduled runs only) | Prevents double-billing on overlapping beats; manual run-now stays unlimited (`scheduled_date=NULL`). Mirrors `run_postmortem`'s atomic claim |
| Market context | Capture a `breadth`-only snapshot | Lighter than a full multi-section capture; `fetch_market_context()` under the hood gives SPX/QQQ/VIX/sectors/breadth |

## Architecture

```
                 BriefingConfig (singleton: enabled, send_at_local, profile, lookback knobs)
                          │
 briefing.run_scheduled (beat, ~15min)            POST /api/briefings/run/ (run-now)
   if enabled & now≥send_at & not-claimed-today          │
                          └──────────────┬───────────────┘
                                         ▼
                              run_briefing(scheduled: bool)
                                         │
            ┌────────────────────────────┼───────────────────────────────┐
            ▼                            ▼                                 ▼
   claim BriefingRun           assemble(config) — gathers:        synthetic user Message
   (scheduled_date unique       theses status (Thesis+quotes)      in briefing Thread
    on scheduled runs)          upcoming_events() [feature #1]     → run_ai_on_message.delay
                                TriggerFiring (overnight)          (best-effort AI synthesis,
                                fetch_news (overnight)              cost-capped, streams via WS)
                                capture(source="briefing")                 │
                                         │                                 ▼
                                         ▼                         synthesis_message FK
                                BriefingRun.data + .snapshot        notify(kind="briefing")
                                         │
                              GET /api/briefings/latest/  ◀── /briefing page (cards + synthesis)
```

### 1. Models — `apps/briefing/models.py`

```python
class BriefingConfig(models.Model):
    """Singleton config for the daily briefing. Use BriefingConfig.load()."""
    enabled = models.BooleanField(default=True)
    send_at_local = models.TimeField(default=time(8, 30))
    profile = models.ForeignKey("profiles.TradingProfile", null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="+")
    news_lookback_hours = models.PositiveIntegerField(default=14)
    events_within_days = models.PositiveIntegerField(default=7)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> "BriefingConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BriefingRun(models.Model):
    STATUS = [("assembling", "Assembling"), ("ready", "Ready"), ("failed", "Failed")]
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default="assembling")
    data = models.JSONField(default=dict)  # assembled deterministic sections
    snapshot = models.ForeignKey("snapshots.Snapshot", null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")
    synthesis_message = models.ForeignKey("threads.Message", null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name="+")
    # Set ONLY on scheduled runs → unique once-per-day claim. NULL for manual run-now (unlimited).
    scheduled_date = models.DateField(null=True, blank=True, unique=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
```

Timezone: `send_at_local` and `scheduled_date` are evaluated in `settings.OBSERVER_BEAT_TIMEZONE` (the existing ET-aware setting), so "today" and the fire time match the user's market day.

### 2. Assembly — `apps/briefing/services/assemble.py`

`assemble(config) -> tuple[dict, Snapshot | None]` gathers the deterministic sections. The `data` dict shape (also the frontend contract):

```python
{
  "theses": [{"id", "ticker", "direction", "conviction", "entry", "target",
              "invalidation", "current", "pct_to_target", "pct_to_invalidation"}],
  "events": {"earnings": [...], "macro": [...]},        # upcoming_events()
  "triggers": [{"trigger_id", "name", "fired_at", "summary"}],  # describe(matched_values)
  "news": [{"headline", "source", "url", "published_at", "ticker"}],
  "market": {"spx_last", "qqq_last", "vix_last", "sectors", "breadth"},  # from the snapshot
  "since": "<iso ts the overnight window started>",
}
```

- **Theses:** `Thesis.objects.filter(status="open")`; one `fetch_quotes(distinct tickers)` call; `pct_to_target = (target-current)/current` etc. (None when prices missing — never raises).
- **Events:** `upcoming_events(watchlist_union, within_days=config.events_within_days)`.
- **Triggers/news window (`since`):** the most recent prior `BriefingRun(status="ready").created_at`, else `now - 24h`.
- **Triggers:** `TriggerFiring.objects.filter(fired_at__gte=since).select_related("trigger")` → `apps.triggers.services.describe.describe(...)`.
- **News:** `fetch_news(watchlist_union, lookback_hours=config.news_lookback_hours)`.
- **Market:** `capture(profile=config.profile, objective="Morning briefing market context", includes=["breadth"], source="briefing", watchlist_tickers=watchlist_union)`; the returned snapshot's `breadth` section payload populates `market`.

`watchlist_union` = distinct `WatchlistSymbol.ticker`. Each gather is wrapped defensively; a failed section yields an empty list/dict + a logged warning (partial briefing is acceptable, like snapshot capture).

### 3. Orchestration — `apps/briefing/services/run.py`

```python
def run_briefing(*, scheduled: bool) -> BriefingRun | None:
    cfg = BriefingConfig.load()
    if scheduled:
        today = _local_today()
        try:
            run = BriefingRun.objects.create(scheduled_date=today, status="assembling")
        except IntegrityError:
            return None          # already claimed today
    else:
        run = BriefingRun.objects.create(scheduled_date=None, status="assembling")

    data, snapshot = assemble(cfg)
    run.data, run.snapshot, run.status = data, snapshot, "ready"
    run.save()

    profile = cfg.profile or TradingProfile.objects.first()
    if profile is not None:           # data-only briefing when no profile exists at all
        thread = get_or_create_briefing_thread(profile)
        msg = Message.objects.create(thread=thread, role="user",
                                     content={"text": render_briefing_markdown(data)},
                                     snapshot_ref=snapshot, status="done")
        run.synthesis_message = msg
        run.save(update_fields=["synthesis_message"])
        run_ai_on_message.delay(thread_id=thread.id, user_message_id=msg.id)

    notify(user_id=None, kind="briefing", title="Your morning briefing is ready",
           body=_one_line_summary(data), link="/briefing")
    return run
```

The AI synthesis is best-effort: the briefing thread's `profile` drives the provider/model (no override needed — same as observer threads), and `run_ai_on_message` enforces cost caps and emits a capability/cost message if it can't run; the `BriefingRun` is already `ready` with its data sections regardless. If no `TradingProfile` exists at all, the synthesis is skipped and the briefing is data-only. `get_or_create_briefing_thread(profile)` mirrors `get_or_create_observer_thread` with `kind="briefing"`. `render_briefing_markdown(data)` renders the assembled sections to a compact markdown prompt prefixed with a "synthesize what matters today, be concise, lead with the most actionable item" instruction. If `run_briefing` raises before reaching `ready` (defensive assembly makes this rare), the run is marked `failed` with `error` set; the scheduled claim still holds (one scheduled attempt/day — the user can `Run now`).

### 4. Scheduling — `apps/briefing/tasks.py` + `config/celery.py`

`@shared_task(name="briefing.run_scheduled")` fires the briefing when due:

```python
@shared_task(name="briefing.run_scheduled")
def run_scheduled() -> dict:
    cfg = BriefingConfig.load()
    if not cfg.enabled:
        return {"skipped": "disabled"}
    now_local = _now_local()
    if now_local.time() < cfg.send_at_local:
        return {"skipped": "before_send_at"}
    run = run_briefing(scheduled=True)   # idempotent claim handles already-ran-today
    return {"ran": run.id if run else None}
```

Beat entry `crontab(minute="*/15")`. `apps.briefing` added to the explicit `autodiscover_tasks([...])` list in `config/celery.py`. **Ops:** `docker compose restart worker beat` after adding (worker/beat don't hot-reload).

### 5. API — `apps/briefing/{serializers,views,urls}.py`

- `GET /api/briefings/` — recent `BriefingRun`s (latest first, paginated/limited).
- `GET /api/briefings/latest/` — the most recent run (+ its synthesis message text/status).
- `POST /api/briefings/run/` — `run_briefing(scheduled=False)`; returns the new run.
- `GET|PATCH /api/briefings/config/` — the singleton `BriefingConfig`.

Function views + DRF serializers as fits each (read endpoints can return `JsonResponse` like the market endpoints; config uses a small serializer). Included in `config/urls.py` as `path("api/briefings/", include("apps.briefing.urls"))` placed **before** the generic `/api/` include (URL-ordering convention).

### 6. Cross-app touches (small migrations)

- `threads.Thread.KIND_CHOICES` += `("briefing", "Briefing")` — migration on `apps.threads`.
- `observer.Notification.KIND_CHOICES` += `("briefing", "Briefing")` — migration on `apps.observer`.

Both are choices-only additions (no schema column change beyond the choices metadata; Django records them in a migration but the DB `varchar` is unchanged).

### 7. Frontend

- **`/briefing` page** (`BriefingPage.tsx`): header (briefing date + **Run now** button calling `POST /run/`) → **AI synthesis** (the `synthesis_message`, rendered markdown; if its status is streaming, subscribe to the existing `thread.<id>` WS for live tokens) → deterministic **cards**: Theses (table: ticker · direction · current · →target% · →invalidation% · conviction), Upcoming events, Overnight triggers, Overnight news, Market context. Built from `Skeleton`/`EmptyState`.
- **Client + hooks** (`frontend/src/api/briefing.ts`, `frontend/src/hooks/useBriefing.ts`): `useLatestBriefing`, `useRunBriefing` (mutation + invalidates latest), `useBriefingConfig` (get/patch).
- **Wiring:** route (`{ path: "briefing", element: <BriefingPage/>, handle: { crumb: "Briefing" } }`), SideNav entry, `go-briefing` Cmd-K command, `b` in `SHORTCUTS` (verified free: existing keys are d/s/t/h/c/o/a/j/e). The `NotificationBell` renders the new `"briefing"` kind generically (title/body/link).

### 8. Testing

- **Assemble** (`test_assemble.py`): theses `pct_to_target`/`pct_to_invalidation` math (+ None when no price); `since` window selection (prior ready run vs 24h); triggers/news/events gathering with mocks; snapshot capture invoked with `source="briefing"`. Defensive: a failing section → empty + logged, never raises.
- **Run** (`test_run.py`): scheduled idempotent claim (2nd same-day scheduled call → `None`); manual run-now always creates; `BriefingRun` lifecycle to `ready`; `synthesis_message` linked + `run_ai_on_message` dispatched; `notify` called with `kind="briefing"`.
- **Beat** (`test_tasks.py`): fires when enabled + `now ≥ send_at` + unclaimed; skips when disabled / before send-at / already-claimed.
- **API** (`test_endpoints.py`): latest/list/run/config contracts.
- **Frontend** (`vitest`): `BriefingPage` render (loading/empty/populated), `useRunBriefing` mutation, config hook.

### 9. Ops & migrations

- New app migrations: `apps/briefing/migrations/0001_initial.py` (`BriefingConfig` + `BriefingRun`, both reversible `CreateModel`; `scheduled_date` unique). Choices-only migrations on `apps.threads` + `apps.observer`.
- `INSTALLED_APPS += "apps.briefing"`; `autodiscover_tasks` += `"apps.briefing"`; beat entry added.
- `docker compose restart worker beat` after the beat/task addition.
- No new credential or external dependency.

## Implementation order (for the plan)

1. New app scaffold (`apps.briefing`: apps.py/label, INSTALLED_APPS, urls include before `/api/`) + `BriefingConfig` + `BriefingRun` models + migration.
2. Cross-app `KIND_CHOICES` additions (threads + observer) + migrations.
3. `assemble()` service + tests.
4. `render_briefing_markdown()` + `get_or_create_briefing_thread()` + `run_briefing()` + tests.
5. `briefing.run_scheduled` beat task + schedule + tests.
6. API endpoints (latest/list/run/config) + serializers + tests.
7. Frontend: client + hooks, `BriefingPage`, route/nav/command/`g b` shortcut, run-now, with vitest coverage.

Steps 3–7 depend only on steps 1–2.
