# M6 — Observer: Design

**Status:** approved 2026-04-17
**Milestone:** M6 (per main spec §16)
**Predecessor:** M5 (chains+news+images, tag `m5-chains-news-images`)
**Successor:** M7 (event triggers)

## Goal

Let the user schedule periodic snapshot+AI runs against a trading profile (the "observer"), surface fired runs in a per-profile timeline, and notify the user when one fires (in-app bell + optional desktop notification). Honors NYSE market hours, daily cost caps, and per-schedule overrides for objective text and AI provider/model.

## Non-goals

- Event triggers (price/breadth/news conditions firing real-time) — M7.
- Webhook notification sinks — interface placeholder only; no concrete impl.
- Multi-user notification routing — `Notification.user` FK exists for the future, but v1 hard-codes a single user.
- Per-schedule observer threads — Q4 chose one thread per profile; per-schedule threads can come later if multi-schedule profiles get noisy.
- Observer back-pressure / queue rate limiting — single-user low-cadence usage; the existing Celery worker handles bursts fine.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Full notifications surface in M6 (Notification model + WebSocket push + bell icon + OS-permission prompt) | Observer without an in-app signal is invisible. The infrastructure is shared with M7 triggers anyway, so build once. |
| 2 | Cron stored under the hood; UI offers preset picker + advanced cron field | Spec calls for cron; preset picker covers 90% of cases without losing the expressive escape hatch. |
| 3 | `pandas-market-calendars` for NYSE open check | Spec calls for it. Hand-coded calendars miss holidays + half-days; that failure mode wastes AI budget on stale data. |
| 4 | One observer thread per profile (spec §7.1) | Matches spec; simplest mental model. Per-schedule threads is a cheap upgrade later via a `schedule_id` tag on each Message if multi-schedule users ever complain about noise. |
| 5 | `ObserverSchedule` carries `objective_template` + optional `override_provider` + optional `override_model` | Per-schedule cost control (cheap model for high-cadence) + meaningful AI prompts (vs spec's empty objective). |
| 6 | `ObserverSchedule.periodic_task = OneToOneField(PeriodicTask)` | Explicit ORM-typed link; avoids signal-handler magic. Sync calls live at the API boundary. |
| 7 | All three UI surfaces in M6 (`/schedules` CRUD, `/threads/observer/:p` timeline, bell + dropdown) | Each is small; together they make M6 actually usable. Splitting out either UI piece leaves an awkward UX gap. |
| 8 | Cost-cap skip writes a placeholder `Message` in the observer thread (not a `Notification`) | Surfaces where the user looks for observer activity. Avoids notification spam during a budget-blown day. |

## Data model

Three new models, one extension. New app: `apps/observer/`.

### `ObserverSchedule` (in `apps/observer/models.py`)

```python
class ObserverSchedule(models.Model):
    name = models.CharField(max_length=100)
    profile = models.ForeignKey(TradingProfile, on_delete=models.CASCADE,
                                related_name="observer_schedules")
    enabled = models.BooleanField(default=True)
    market_hours_only = models.BooleanField(default=True)
    objective_template = models.TextField(blank=True, default="")
    override_provider = models.CharField(max_length=32, blank=True, default="")
    override_model = models.CharField(max_length=100, blank=True, default="")
    default_includes = models.JSONField(default=list)            # falls back to profile.default_includes when empty
    default_watchlist_tickers = models.JSONField(default=list)   # tickers fed into capture()
    periodic_task = models.OneToOneField(
        "django_celery_beat.PeriodicTask",
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    last_fired_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["profile", "enabled"])]
```

### `Notification` (in `apps/observer/models.py`)

```python
class Notification(models.Model):
    KIND_CHOICES = [
        ("trigger", "Trigger"),
        ("observer_done", "Observer fired"),
        ("error", "Error"),
        ("cost_limit", "Cost limit"),
    ]

    # Nullable for v1 because no user-auth surface exists yet (M4's token-auth path is
    # not implemented). When user-auth lands, backfill or default to the resolved user.
    # The FK is kept so the model is multi-user-ready by shape.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=500, blank=True, default="")
    meta = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "read_at", "-created_at"])]
        ordering = ["-created_at"]
```

### `Thread` extension (in `apps/threads/models.py`)

Add `schedule` FK so `Thread.objects.filter(kind="observer", profile=p, schedule__isnull=True)` resolves the per-profile observer thread cleanly. The FK is nullable; only observer threads ever populate it (and v1 keeps it null because Q4 chose one thread per profile, not per schedule).

```python
schedule = models.ForeignKey(
    "observer.ObserverSchedule", null=True, blank=True,
    on_delete=models.SET_NULL, related_name="threads",
)
```

### Migrations

- New `observer` initial migration: ObserverSchedule + Notification.
- `threads` migration adding the `schedule` FK (string FK to avoid cross-app import order).
- `django_celery_beat` migrations are already applied (M1).

## Service layer

New package `apps/observer/services/`.

### `services/market_hours.py`

```python
import pandas_market_calendars as mcal
from django.utils import timezone

_NYSE = mcal.get_calendar("XNYS")

def is_market_open(at: datetime | None = None) -> bool:
    """Half-day and holiday-aware NYSE regular-session check."""
    now = at or timezone.now()
    sched = _NYSE.schedule(start_date=now.date(), end_date=now.date())
    if sched.empty:
        return False
    open_t = sched.iloc[0]["market_open"].to_pydatetime()
    close_t = sched.iloc[0]["market_close"].to_pydatetime()
    return open_t <= now <= close_t


def market_status(at: datetime | None = None) -> dict:
    """Returns {is_open, next_open, next_close} for the bell tooltip + UI badge."""
    now = at or timezone.now()
    sched = _NYSE.schedule(
        start_date=now.date(),
        end_date=(now + timedelta(days=14)).date(),
    )
    is_open = False
    next_open = next_close = None
    today = sched[sched.index.date == now.date()]
    if not today.empty:
        o = today.iloc[0]["market_open"].to_pydatetime()
        c = today.iloc[0]["market_close"].to_pydatetime()
        is_open = o <= now <= c
        if now < o: next_open = o
        if now < c: next_close = c
    if next_open is None:
        future = sched[sched["market_open"].dt.to_pydatetime() > now]
        if not future.empty:
            next_open = future.iloc[0]["market_open"].to_pydatetime()
    return {"is_open": is_open, "next_open": next_open, "next_close": next_close}
```

### `services/threads.py`

```python
def get_or_create_observer_thread(profile: TradingProfile) -> Thread:
    """Per-Q4: one observer thread per profile, idempotent."""
    obj, _ = Thread.objects.get_or_create(
        profile=profile, kind="observer", schedule__isnull=True,
        defaults={"title": f"Observer: {profile.name}"},
    )
    return obj
```

### `services/run.py`

```python
def run_observer(schedule_id: int) -> int | None:
    """Orchestrates one observer fire. Returns the snapshot id, or None on skip."""
    sched = ObserverSchedule.objects.select_related("profile").get(id=schedule_id)

    if not sched.enabled:
        return None
    if sched.market_hours_only and not is_market_open():
        log.info("observer %s skipped: market closed", schedule_id)
        return None

    thread = get_or_create_observer_thread(sched.profile)
    provider = sched.override_provider or sched.profile.default_provider

    if cost_cap_exceeded(provider):
        Message.objects.create(
            thread=thread, role="system",
            content={"text": f"⏸ Observer fire skipped at {timezone.now():%Y-%m-%d %H:%M UTC}: "
                             f"daily cost cap reached for {provider}."},
            status="done",
        )
        sched.last_fired_at = timezone.now()
        sched.save(update_fields=["last_fired_at"])
        return None

    snap = capture(
        profile=sched.profile,
        objective=sched.objective_template,
        includes=sched.default_includes or sched.profile.default_includes,
        source="observer",
        watchlist_tickers=sched.default_watchlist_tickers,
    )
    msg = Message.objects.create(
        thread=thread, role="user",
        content={"text": serialize_for_ai(snap)},
        snapshot_ref=snap, status="done",
    )
    ai_run_thread.delay(
        thread_id=thread.id, message_id=msg.id,
        override_provider=sched.override_provider or None,
        override_model=sched.override_model or None,
    )
    sched.last_fired_at = timezone.now()
    sched.save(update_fields=["last_fired_at"])

    notify(
        user_id=None,  # v1 single-user, no auth surface yet — Notification.user is nullable
        kind="observer_done",
        title=f"Observer fired: {sched.name}",
        body=f"Snapshot #{snap.id} captured for {sched.profile.name}",
        link=f"/threads/observer/{sched.profile.id}",
    )
    return snap.id
```

### `tasks.py` Celery wrapper

```python
@shared_task(name="observer.run_observer")
def run_observer_task(schedule_id: int):
    return run_observer(schedule_id)
```

### `services/notifications.py`

```python
def notify(*, user_id: int | None, kind: str, title: str, body: str = "",
           link: str = "", meta: dict | None = None) -> Notification:
    n = Notification.objects.create(
        user_id=user_id, kind=kind, title=title, body=body,
        link=link, meta=meta or {},
    )
    # v1 broadcasts on a single anonymous group. When user-auth lands, switch to
    # f"user.{user_id}.notifications".
    group_name = f"user.{user_id}.notifications" if user_id else "user.anonymous.notifications"
    layer = get_channel_layer()
    if layer:
        async_to_sync(layer.group_send)(
            group_name,
            {"type": "notification.event", "payload": NotificationSerializer(n).data},
        )
    return n
```

### Failure modes

- **`pandas_market_calendars` import-fails** → `is_market_open` raises at import; observer surface is broken until the dep is fixed. Loud failure is appropriate (no observer should silently fall back to "always open").
- **AI run path crashes** → `ai_run_thread.delay` already handles errors via the existing thread-task error path. Observer doesn't need its own retry layer.
- **`cost_cap_exceeded`** → placeholder Message + last_fired_at update, no notification.
- **Beat fires while a previous run still pending** → idempotent (each fire creates a new Message + Snapshot; no shared state mutation that would corrupt). Acceptable at single-user cadence.

## Beat sync + lifecycle

### `services/sync.py`

```python
def sync_periodic_task(schedule: ObserverSchedule, *, cron: str) -> PeriodicTask:
    minute, hour, dom, month, dow = cron.split()
    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=minute, hour=hour, day_of_month=dom,
        month_of_year=month, day_of_week=dow,
        timezone=settings.OBSERVER_BEAT_TIMEZONE,
    )
    if schedule.periodic_task is None:
        pt = PeriodicTask.objects.create(
            name=f"observer-schedule-{schedule.id}",
            task="observer.run_observer",
            crontab=crontab,
            kwargs=json.dumps({"schedule_id": schedule.id}),
            enabled=schedule.enabled,
        )
        schedule.periodic_task = pt
        schedule.save(update_fields=["periodic_task"])
    else:
        pt = schedule.periodic_task
        pt.crontab = crontab
        pt.enabled = schedule.enabled
        pt.kwargs = json.dumps({"schedule_id": schedule.id})
        pt.save()
    return pt


def delete_periodic_task(schedule: ObserverSchedule) -> None:
    if schedule.periodic_task_id:
        schedule.periodic_task.delete()
```

**Where called:** the schedules ViewSet calls `sync_periodic_task` after every create/update, and `delete_periodic_task` in `destroy()`. Admin edits go through a small `ModelAdmin.save_model` override that does the same. **No Django signals** — explicit calls at the API boundary so refactors can't drop them silently.

**Beat ↔ DB sync:** `DatabaseScheduler` polls every 5s by default. UI edits propagate within that window.

**Settings**: `OBSERVER_BEAT_TIMEZONE = env("OBSERVER_BEAT_TIMEZONE", default="UTC")`. Cron expressions are evaluated in this zone — most users will want `America/New_York` for NYSE-aligned schedules; default UTC is the safe baseline.

**Cron validation:** the schedules ViewSet validates with `croniter` before save. Invalid → DRF 400 with field error.

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/observer/schedules/` | List schedules |
| POST | `/api/observer/schedules/` | Create (validates cron, syncs PeriodicTask) |
| GET | `/api/observer/schedules/<id>/` | Read one |
| PATCH | `/api/observer/schedules/<id>/` | Edit (re-syncs PeriodicTask) |
| DELETE | `/api/observer/schedules/<id>/` | Delete (deletes PeriodicTask) |
| POST | `/api/observer/schedules/<id>/run-now/` | Manual fire — runs `run_observer(id)` synchronously, skipping `market_hours_only`; returns 202 |
| GET | `/api/observer/notifications/?unread=true&limit=50` | List notifications (v1: filters `user__isnull=True`) |
| POST | `/api/observer/notifications/<id>/read/` | Mark single notification read |
| POST | `/api/observer/notifications/mark-all-read/` | Bulk mark all unread (v1: `user__isnull=True`) |
| GET | `/api/observer/threads/<profile_id>/` | Returns the per-profile observer thread (creates if missing), with messages prefetched |
| GET | `/api/observer/market-status/` | `{is_open, next_open, next_close}` for the bell tooltip + schedules badge |

### Channels routing

`apps/observer/consumers.py` — `NotificationsConsumer` joins `user.anonymous.notifications` group on connect (v1, no auth), pushes `notification.event` group sends as JSON. When user-auth is added, switch to `user.<id>.notifications`.

Routing in `config/routing.py`: `r"^ws/notifications/$" → NotificationsConsumer.as_asgi()`.

### Realtime payload

```json
{"type": "notification.event",
 "payload": {"id": 42, "kind": "observer_done",
             "title": "Observer fired: Day Trader",
             "body": "Snapshot #123 captured for Day Trader",
             "link": "/threads/observer/3",
             "created_at": "2026-04-17T13:35:02Z"}}
```

Frontend pushes payload to local state and increments unread counter.

## Frontend

Three pieces: `/schedules` CRUD, `/threads/observer/:profileId` timeline, top-nav bell.

### `/schedules` — `SchedulesPage.tsx`

- **Top:** list of existing schedules. Each card: name, profile name, cron + plain-English (`cronstrue`), enabled toggle (immediate PATCH), "Run now" button → POSTs `/run-now/`, edit / delete.
- **Bottom:** "+ New schedule" button reveals an inline create form.
- **Form fields:**
  - name (text)
  - profile picker (existing `useProfiles`)
  - enabled checkbox
  - market_hours_only checkbox
  - cron-mode toggle: **Preset** (radio: `Every 5min`, `Every 15min`, `Hourly`, `Daily 9:35 ET`, `Daily 16:00 ET` mapping to canned crons) **/ Advanced** (free-text cron field)
  - live preview of the resulting cron + plain-English via `cronstrue`
  - objective_template textarea
  - override_provider dropdown (existing `useProviderConfigs`, blank = profile default)
  - override_model dropdown (existing `useAiModels`, blank = provider default)
  - default_includes (reuse M5's `SnapshotSectionPicker`)
  - default_watchlist_tickers picker

### `/threads/observer/:profileId` — `ObserverTimelinePage.tsx`

Read-only timeline of the per-profile observer thread.

- **Header:** profile name, schedule status chips (one per schedule for this profile, "enabled / disabled / next fire in X"), "Open settings" link to `/schedules`.
- **Body:** messages list, newest first. Each message collapsible:
  - Collapsed: headline (e.g. `"📷 Snapshot #123 — 2026-04-17 09:35 UTC — Day Trader observer"`)
  - Expanded: full assistant response rendered with `react-markdown` (existing `StreamingMessage`-style render).
  - Skipped firings (cost-cap from Q8) render as muted gray rows with the lock icon.
- **Auto-refresh:** subscribes to the `thread.<id>` channel; new messages animate in.

### `<NotificationBell />` in top nav

- Unread badge count (red dot when > 0).
- Click → dropdown panel with last 50 notifications, newest first. Each is a clickable row → marks read + navigates to `link`.
- "Mark all read" button at the bottom.
- On mount, fetches `/api/observer/notifications/?limit=50` once + subscribes to `ws/notifications/`.
- **OS-permission prompt:** if `Notification.permission === "default"` and the user opens the dropdown, show a one-time banner: "Get a desktop notification when the AI fires? [Enable] [Not now]". `[Enable]` calls `Notification.requestPermission()`. After grant, every WebSocket-pushed notification with `kind ∈ {observer_done, trigger}` triggers `new Notification(title, {body})`.

### Routes

`router.tsx` additions:
- `/schedules` → `SchedulesPage`
- `/threads/observer/:profileId` → `ObserverTimelinePage`

Bell mounted in the existing nav layout component.

### New deps

`frontend/package.json`:
- `cronstrue ^2.50.0` (MIT) — pure-JS cron → English

## Testing

### Backend unit tests

- `apps/observer/tests/test_market_hours.py` — `is_market_open` returns `True` mid-session weekday, `False` Saturday, `False` 4 Jul 2026, correct half-day handling (Black Friday early close at 13:00 ET). Uses `freezegun` to pin times.
- `apps/observer/tests/test_threads.py` — `get_or_create_observer_thread` returns the same Thread on repeat call for same profile; isolates per-profile.
- `apps/observer/tests/test_run_observer.py` — orchestration tests with all externals mocked:
  - `enabled=False` → returns None, no snapshot
  - `market_hours_only=True` + market closed → returns None, no snapshot
  - cost cap exceeded → placeholder Message written, no snapshot, last_fired_at updated, no notification
  - happy path → snapshot created (source="observer"), Message attached, ai_run_thread.delay called with right kwargs, notify() called once, last_fired_at updated
- `apps/observer/tests/test_sync.py` — `sync_periodic_task`:
  - First call creates `CrontabSchedule` + `PeriodicTask` + sets schedule.periodic_task FK
  - Second call updates existing PeriodicTask (no orphans)
  - `delete_periodic_task` removes the PeriodicTask but leaves the CrontabSchedule
- `apps/observer/tests/test_notifications_service.py` — `notify` writes a row + broadcasts on `user.<id>.notifications` channel via `InMemoryChannelLayer`.

### Backend integration tests

- `apps/observer/tests/test_schedules_endpoint.py` — full CRUD: create with valid cron → 201 + PeriodicTask exists; create with invalid cron `"bogus"` → 400 with field error; PATCH `enabled=false` → 200 + linked PeriodicTask.enabled flipped; DELETE → 204 + PeriodicTask gone; POST `/run-now/` → 202.
- `apps/observer/tests/test_notifications_endpoint.py` — list filters by `?unread=true`; `read/` flips `read_at`; `mark-all-read/` updates the queryset.
- `apps/observer/tests/test_market_status_endpoint.py` — endpoint returns expected shape.
- `apps/observer/tests/test_observer_thread_endpoint.py` — `GET /api/observer/threads/<profile_id>/` returns the thread (creates on first call), prefetches messages.

### Channels test

- `apps/observer/tests/test_consumer.py` — open `ws/notifications/`, broadcast a fake notification on `user.1.notifications`, assert the consumer pushes it.

### Frontend tests (vitest + RTL)

- `SchedulesPage.test.tsx` — list renders; create form posts with cron from preset; toggle posts PATCH; delete removes from list.
- `ObserverTimelinePage.test.tsx` — renders messages; collapsing/expanding works.
- `NotificationBell.test.tsx` — badge shows unread count from initial fetch; WebSocket-pushed notification increments badge; clicking row marks read; "mark all read" button zeros badge.
- `cronPreview.test.tsx` — small wrapper test verifying `cronstrue` integration produces expected English for the canned presets.

### Smoke verification

- Frontend routes 200: existing M5 set + `/schedules`, `/threads/observer/1`.
- Backend endpoints work: `/api/observer/schedules/` (200, empty), `/api/observer/notifications/?unread=true` (200, empty), `/api/observer/market-status/` (200 with shape).
- Manual: create a schedule via UI → toggle enabled → click "Run now" → observer thread page shows new entry within 5s.

### Cold rebuild + tag

- `make check` green
- `git tag m6-observer`

## Out of scope (deferred to later milestones)

- Event triggers (price/breadth/news real-time evaluation) — M7
- Webhook notification sinks
- Multi-user notification routing
- Per-schedule observer threads
- Observer back-pressure / queue limits
- Calendar sources beyond NYSE (CME, options)
