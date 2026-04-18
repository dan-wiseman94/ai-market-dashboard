# M7 — Event triggers: Design

**Status:** approved 2026-04-18
**Milestone:** M7 (per main spec §16)
**Predecessor:** M6 (observer + notifications, tag `m6-observer`)
**Successor:** M8 (polish — multi-provider compare, costs dashboard, backups, export, E2E)

## Goal

Let the user define condition-based rules that watch live market metrics and automatically fire a snapshot + AI analysis + notification when the rule's condition becomes true. Rules are defined via a guided visual builder, stored as a validated JSON DSL, and evaluated on a short beat-scheduled tick (10s, market-hours only). Matches main spec §4.6, §4.8, §7.2, §7.3, §8.6.

## Non-goals

- Historical back-testing or replay of conditions — evaluator is live-only; past `TriggerFiring` rows are audit, not simulation state.
- `volume_z(window)` metric — deferred to M8 (requires a volume-history store that doesn't exist yet).
- Nested condition groups in the UI — the DSL supports arbitrary nesting via recursion, but the builder emits at most one top-level `all|any` over flat leaves (matches spec §8.6).
- The `not` operator in the UI — DSL supports it, builder doesn't expose it. YAGNI for v1.
- Multi-user notification routing — reuses M6's anonymous-user path; `Notification.user` FK stays nullable.
- Webhook / Slack / email sinks — the `notify()` service from M6 has one WebSocketSink impl; other sinks are M8+.
- Cross-profile global triggers — every trigger is scoped to a `TradingProfile` (required FK, see Decision 6).

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Ship metrics: `price`, `pct_change(window)`, `vix`, `position_pl`, `position_pl_pct`. Skip `volume_z`. | `volume_z` needs a volume-history ring buffer that doesn't exist; the other five run straight off existing quotes + positions services from M2/M5. Covers "SPY crossed 550", "NVDA +2% in 5m", "portfolio down $X" without net-new plumbing. |
| 2 | Beat tick at 10s, **market-hours only** (reuses `observer.services.market_hours.is_market_open`). | Mirrors observer-schedule gating; no pointless Schwab calls overnight or on holidays. Overnight news-driven rules would need a separate `NewsItem`-driven path, out of scope for M7. |
| 3 | Tick fetches quotes only for the union of tickers across enabled triggers' leaves; positions only if any active trigger uses `position_pl*`. | Minimum Schwab load; no orphan data. Positions is a separate API call, pay for it only when needed. |
| 4 | Crossing operators (`crosses_above` / `crosses_below`) read "previous tick" from a Redis key (`trigger:last:<TICKER>`, TTL 60s). No Postgres history table. | Crossings are edge-triggered UX, not audit; one missed edge per eviction is acceptable. Redis already load-bearing for cache + Channels. A dedicated `TriggerMetricTick` table would grow unboundedly for zero long-term value. |
| 5 | Cooldown = time gate **AND** re-arm gate. Trigger can fire again only when both `(now - last_fired_at) > cooldown_seconds` AND the condition has evaluated `False` at least once since the last fire. | Prevents repeat-firing on a sticky condition ("SPY stays above 550 for an hour"). Matches user expectation that one event = one notification. |
| 6 | `EventTrigger.profile` is a **required** FK. No cross-profile global triggers. | Resulting snapshot + AI run need a profile (style text, default provider). "Use first enabled" is ambiguous; "fan out across every profile" is expensive and not what users want. Aligns with schedules (M6). |
| 7 | Visual rule builder: form rows with natural-language echo. No raw JSON editor in v1. | Plain-English restatement per row ("SPY moved ≥1% over 5m") confirms user intent without exposing DSL syntax. Raw-JSON editor is fast to build but miserable to use; live JSON preview is clutter once the shape is stable. |
| 8 | Notifications on fire: WebSocket bell entry + in-app toast + **OS desktop notification** (reusing M6's permission prompt and `Notification.kind="trigger"` path). | OS-notification plumbing is already paid for in M6. Using it for triggers is the specific use case spec §8.7 planned. No auto-open-tab (unexpected tab-switching is an antipattern). |
| 9 | Cost-cap policy: fire snapshot, **skip AI call**, create `Notification(kind="cost_limit")`. | Matches spec §5.6. Snapshot is pennies; AI is the expensive part. User retains audit trail + can replay manually by opening the thread later. |
| 10 | Manual test tooling: **both** `POST /api/triggers/<id>/fire/` (run full fire path) and `POST /api/triggers/evaluate/` (run evaluator only, no side effects). | `fire` for "show me what happens"; `evaluate` for "did I write the condition right". The builder uses `evaluate` to show a live "would currently fire: YES/NO" preview. |
| 11 | Firings history surface: `/triggers/:id` drill-down with paginated table + `RecentTriggersCard` on the dashboard showing last 5 firings globally. | `last_fired_at` alone buries activity; a cross-trigger page (`/triggers/firings`) is future polish. The dashboard widget covers "anything interesting today?" at a glance. |
| 12 | Evaluator is a pure function with zero I/O. Metrics fetching lives in a separate `metrics.py` module that populates a plain `dict`, which the evaluator consumes. | Matches spec §7.3 verbatim. Clean test boundary: evaluator gets a dict literal, no mocks. The Schwab/Redis complexity is localized to one file (`metrics.py`). |
| 13 | `fire_trigger` Celery task is **not** auto-retried. On failure, log + one-shot `kind="error"` notification. Defensive `redis_lock` in the task prevents manual replay duplicates. | Retry semantics would double-fire (duplicate `TriggerFiring`, duplicate snapshot, duplicate notification). Re-arm gate + cooldown + redis_lock combined make duplicate fires nearly impossible. |
| 14 | Invalid-DSL triggers get auto-disabled, not deleted. User sees "disabled — invalid condition" on `/triggers`. | Validation runs on save, so DB state should always be valid; if it somehow isn't (manual DB edit, migration, bug), the tick must not hot-loop on the broken row. Disabling keeps it visible for manual fix. |

## Architecture

New Django app: **`apps.triggers`**. File layout:

```
backend/apps/triggers/
  __init__.py
  apps.py                      # AppConfig (label="triggers")
  migrations/
    0001_initial.py            # EventTrigger + TriggerFiring
  models.py                    # EventTrigger, TriggerFiring
  serializers.py               # DRF serializers + DSL validation
  views.py                     # DRF ViewSet + custom actions
  urls.py                      # /api/triggers/, nested /firings/
  dsl.py                       # validate_condition(node) → raises ValidationError
  evaluator.py                 # pure evaluate(node, metrics) → (bool, dict)
  metrics.py                   # build_snapshot(triggers) → MetricsSnapshot
  services/
    __init__.py
    cooldown.py                # cooldown_blocks, mark_fired, mark_rearmed
    describe.py                # describe(matched_values) → human-readable string
  tasks.py                     # evaluate_triggers (beat), fire_trigger (async)
  tests/
    __init__.py
    test_evaluator.py          # parametrized op × metric table
    test_dsl_validation.py     # reject invalid shapes
    test_metrics.py            # snapshot construction
    test_cooldown.py           # time + re-arm gates
    test_evaluate_triggers_task.py
    test_fire_trigger_task.py
    test_endpoints.py          # CRUD + fire + evaluate
    test_recent_firings_endpoint.py
```

Wiring:
- Add `"apps.triggers"` to `INSTALLED_APPS`.
- Add `path("api/triggers/", include("apps.triggers.urls"))` to `config/urls.py` **before** the generic `/api/` includes (known convention, CLAUDE.md).
- Register `evaluate_triggers` in `config/celery.py`'s explicit task list (CLAUDE.md note: autodiscovery is not trusted).
- Add a `django-celery-beat` `PeriodicTask` seeded via data migration: interval = `TRIGGER_TICK_SECONDS` (default 10), task = `triggers.evaluate_triggers`, enabled by default.

Integration points (reused, not rebuilt):
- `apps.market.services.quotes.fetch_quotes`
- `apps.market.services.positions.fetch_positions`
- `apps.observer.services.market_hours.is_market_open`
- `apps.snapshots.services.capture`
- `apps.observer.services.notifications.notify` (M6)
- `apps.ai.cost.CostCapExceededError` / provider lookup (already used by `threads.tasks`)

## Data model

Two new tables, both in `apps.triggers`. No changes to existing models — `Snapshot.source` already supports `"trigger"` (M3) and `Notification.kind` already supports `"trigger"` / `"cost_limit"` (M6).

### `EventTrigger`

```python
class EventTrigger(models.Model):
    name             = models.CharField(max_length=100)
    profile          = models.ForeignKey("profiles.TradingProfile", on_delete=models.CASCADE,
                                         related_name="triggers")
    condition        = models.JSONField()           # validated via dsl.validate_condition
    cooldown_seconds = models.PositiveIntegerField(default=1800)
    enabled          = models.BooleanField(default=True)
    last_fired_at    = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["enabled", "-last_fired_at"])]
        constraints = [models.UniqueConstraint(fields=["profile", "name"],
                                               name="unique_trigger_name_per_profile")]

    def clean(self):
        from apps.triggers.dsl import validate_condition
        validate_condition(self.condition)
```

### `TriggerFiring`

```python
class TriggerFiring(models.Model):
    trigger        = models.ForeignKey(EventTrigger, on_delete=models.CASCADE,
                                       related_name="firings")
    fired_at       = models.DateTimeField(auto_now_add=True)
    matched_values = models.JSONField()          # {"price:SPY": 551.12, ...}
    snapshot       = models.ForeignKey("snapshots.Snapshot",
                                       null=True, on_delete=models.SET_NULL,
                                       related_name="trigger_firings")
    thread         = models.ForeignKey("threads.Thread",
                                       null=True, on_delete=models.SET_NULL,
                                       related_name="trigger_firings")
    cost_capped    = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["trigger", "-fired_at"]),
            models.Index(fields=["-fired_at"]),
        ]
```

## Condition DSL

Stored on `EventTrigger.condition` as JSON. Shape (v1 frozen):

```json
{"all|any": [<node>, ...]}                 // group nodes
{"not": <node>}                            // negation wraps exactly one node
{                                          // leaf node
  "metric": "price" | "pct_change" | "vix" | "position_pl" | "position_pl_pct",
  "ticker": "<SYMBOL>",                    // required except for vix/position_* (ignored/omitted)
  "op":     ">" | ">=" | "<" | "<=" | "==" | "crosses_above" | "crosses_below",
  "value":  <number>,
  "window": "1m" | "5m" | "15m" | "1h" | "1d"   // required for pct_change; forbidden otherwise
}
```

Metrics catalog (v1):

| metric | ticker? | window? | source |
|---|---|---|---|
| `price` | required | — | Schwab quote `.last` |
| `pct_change` | required | required | `(now.last − prior_window.last) / prior_window.last` |
| `vix` | ignored (forced to `$VIX`) | — | Schwab quote for `$VIX` |
| `position_pl` | ignored | — | `sum(fetch_positions()[*].unrealized_pl)` |
| `position_pl_pct` | ignored | — | `sum(unrealized_pl) / sum(mkt_value)` |

DSL validation (`apps/triggers/dsl.py`):

```python
def validate_condition(node: Any, *, path: str = "") -> None:
    """Raise ValidationError with path info on invalid shape.
    Called from EventTrigger.clean() and the DRF serializer."""
```

Runs at save time; keeps invalid JSON out of the database. Validator is itself pure and recursive.

## Evaluator

File: `apps/triggers/evaluator.py`. Pure function, no I/O:

```python
MetricsSnapshot = Mapping[str, float | None]

def evaluate(node: dict, metrics: MetricsSnapshot) -> tuple[bool, dict[str, float | None]]:
    """Return (matched, matched_values).

    matched_values is the set of metric keys the evaluator actually read from
    `metrics` during this evaluation — populates the notification body and
    the TriggerFiring.matched_values audit column.

    Leaves that read a `None` metric return False (never raise). This makes
    trigger rules forgiving of missing data: a `pct_change` with no prior
    window observation simply doesn't fire, rather than erroring the tick.
    """
```

Recursive, short-circuits on `all`/`any`. Leaf dispatcher resolves the metric key using `(metric, ticker, window)`; the key format is the flat string scheme below.

### Metrics-snapshot key format

```
"price:SPY"                  → float | None
"pct_change:SPY:5m"          → float | None
"vix"                        → float | None
"position_pl"                → float | None
"position_pl_pct"            → float | None
"_prior:price:SPY"           → float | None      # used only by crosses_* operators
```

`_prior:` entries are populated by `metrics.py` from Redis before the evaluator runs.

### Crossing operators

- `crosses_above`: `_prior <= value` AND current `> value`.
- `crosses_below`: `_prior >= value` AND current `< value`.
- If either side is `None`, leaf returns `False` (no data → no edge).

## Metrics builder

File: `apps/triggers/metrics.py`. One public function:

```python
def build_snapshot(triggers: Iterable[EventTrigger]) -> MetricsSnapshot:
    """Builds the MetricsSnapshot for one beat tick. Steps:

    1. Walk all `triggers[*].condition` trees; collect distinct (metric, ticker, window) leaves.
    2. Determine ticker union + whether any position_* metric is referenced.
    3. One `fetch_quotes()` batch for the union; conditional `fetch_positions()`.
    4. For every `crosses_*` leaf, read Redis `trigger:last:<TICKER>` to populate `_prior:price:<TICKER>`.
    5. For every `pct_change(window)` leaf, read Redis `trigger:window:<TICKER>:<window>`
       (a per-window prior observation snapshotted every `window` seconds) to compute the delta.
    6. Stamp current `last` back to `trigger:last:<TICKER>` (TTL 60s).
    7. Refresh window-prior keys on window expiry; each window key has TTL = 2 × window_seconds.
    8. Return the dict.

    On any Schwab / Redis failure: log, return None-filled snapshot for the affected keys.
    The tick proceeds; downstream leaves read None and return False. No fire happens
    from partial data.
    """
```

Redis key layout:

```
trigger:last_tick_at                  → unix-seconds of most recent tick       (TTL 120s)
trigger:last:<TICKER>                 → most recent last price                 (TTL 60s)
trigger:window:<TICKER>:<window>      → last price at start of current window  (TTL 2 × window_seconds)
trigger:armed:<trigger_id>            → "1" if re-armed after fire             (TTL 1 day)
trigger:fire:<trigger_id>             → redis_lock during fire_trigger         (auto-released)
```

## Cooldown gate

File: `apps/triggers/services/cooldown.py`. Implements Decision 5 (time **AND** re-arm).

```python
def cooldown_blocks(trigger: EventTrigger) -> bool:
    """True → skip this trigger for this tick."""
    # Time gate
    if trigger.last_fired_at:
        elapsed = (timezone.now() - trigger.last_fired_at).total_seconds()
        if elapsed < trigger.cooldown_seconds:
            return True
    # Re-arm gate: block until condition has gone False at least once since last fire
    if trigger.last_fired_at and not redis_client().exists(f"trigger:armed:{trigger.id}"):
        return True
    return False

def mark_fired(trigger_id: int) -> None:
    redis_client().delete(f"trigger:armed:{trigger_id}")

def mark_rearmed(trigger_id: int) -> None:
    redis_client().setex(f"trigger:armed:{trigger_id}", 86400, "1")
```

Evaluator flow within `evaluate_triggers`:
- Condition `False` → call `mark_rearmed(id)`.
- Condition `True` AND not in cooldown → call `mark_fired(id)`, enqueue `fire_trigger.delay(id, values)`.
- Condition `True` AND in cooldown → no-op (skip).

## Data flow

### Beat tick

```
django-celery-beat fires every TRIGGER_TICK_SECONDS (default 10s)
  → tasks.evaluate_triggers (single_instance=True via Redis lock)
      1. if not market_hours.is_market_open(): return
      2. triggers = list(EventTrigger.objects.filter(enabled=True).select_related("profile"))
      3. if not triggers: return
      4. snapshot = metrics.build_snapshot(triggers)
      5. for trigger in triggers:
           if cooldown.cooldown_blocks(trigger): continue
           matched, values = evaluator.evaluate(trigger.condition, snapshot)
           if not matched:
               cooldown.mark_rearmed(trigger.id)
               continue
           cooldown.mark_fired(trigger.id)
           fire_trigger.delay(trigger.id, values)
      6. structlog.info("trigger.tick", triggers_evaluated=n, fires_enqueued=k, duration_ms=...)
```

### `fire_trigger(trigger_id, matched_values)`

```
with redis_lock(f"trigger:fire:{trigger_id}", timeout=60):
    trigger = EventTrigger.objects.get(id=trigger_id)
    firing = TriggerFiring.objects.create(
        trigger=trigger, matched_values=matched_values,
    )
    trigger.last_fired_at = timezone.now()
    trigger.save(update_fields=["last_fired_at", "updated_at"])

    try:
        snap = snapshots.capture(
            profile=trigger.profile,
            includes=trigger.profile.default_includes,
            source="trigger",
            notes=f"Triggered: {trigger.name}",
        )
    except Exception as exc:
        logger.error("trigger.fire.capture_failed", trigger_id=trigger.id, error=str(exc))
        notify(kind="error", title=f"{trigger.name} fired — snapshot failed",
               body=str(exc), link=f"/triggers/{trigger.id}")
        return

    firing.snapshot = snap
    firing.save(update_fields=["snapshot"])

    # Cost-cap check uses the same primitives as threads.run_ai_on_message. The
    # profile's default_provider is the answer pre-routing; any Thread.default_provider
    # override is moot here because we haven't created the thread yet. We only need to
    # block the expensive call, so this simpler path suffices.
    provider_name = trigger.profile.default_provider
    cfg = ProviderConfig.objects.get(provider=provider_name)
    try:
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
    except CostCapExceededError as exc:
        firing.cost_capped = True
        firing.save(update_fields=["cost_capped"])
        notify(kind="cost_limit",
               title=f"{trigger.name} fired — AI skipped (cap hit)",
               body=f"{describe(matched_values)} · {exc}",
               link=f"/triggers/{trigger.id}")
        return

    thread = Thread.objects.create(
        kind="chat", profile=trigger.profile, pinned_snapshot=snap,
        title=f"{trigger.name} fired at {timezone.localtime():%H:%M}",
    )
    firing.thread = thread
    firing.save(update_fields=["thread"])

    # Reuse existing /threads/<id>/send code path: create a user Message containing
    # the serialized snapshot, enqueue run_ai_on_message.
    user_msg = Message.objects.create(
        thread=thread, role="user", status="done",
        content={"text": serialize_for_ai(snap)},
    )
    run_ai_on_message.delay(thread_id=thread.id, user_message_id=user_msg.id)

    notify(kind="trigger",
           title=trigger.name,
           body=describe(matched_values),
           link=f"/threads/{thread.id}")
```

`describe(matched_values)` formats `{"price:SPY": 551.2}` → `"SPY=551.20"`. Single-line helper in `services/describe.py`.

### Manual endpoints

- `POST /api/triggers/<id>/fire/` → validates trigger exists and is enabled, enqueues `fire_trigger.delay(id, {"source": "manual"})`, returns `202 {firing_id: null, task_id}`. Confirm dialog in the UI.
- `POST /api/triggers/evaluate/` → body `{condition}` (or `{trigger_id}` for saved rules). Builds a single-trigger `MetricsSnapshot`, runs `evaluator.evaluate`, returns `{matched: bool, values: dict, missing: list[str]}` where `missing` lists metric keys that came back `None`. No firing, no notification. Used by the builder's debounced live preview.

## Error handling

| Failure | Where | Handling |
|---|---|---|
| Schwab API 429 / 503 during metrics build | `metrics.py` | Tick logs warning, returns early without any fires. Next tick retries. No partial snapshot — prevents spurious non-matches on `all` groups. |
| Single ticker missing from quote response | `metrics.py` | That ticker's keys are `None` in the snapshot. Any leaf reading it returns `False`. Rule simply doesn't fire. |
| Redis unavailable | `metrics.py` / `cooldown.py` | Tick logs error and aborts. Abort > fire-incorrectly. |
| Invalid condition JSON in DB (shouldn't happen, validated on save) | `evaluator.py` | Raises `ValidationError`; caught per-trigger in `evaluate_triggers`. Logs error, sets `trigger.enabled = False`, continues tick. User sees "disabled — invalid condition" banner on `/triggers`. |
| `capture()` fails during fire | `tasks.fire_trigger` | `firing.snapshot` stays `None`. `notify(kind="error")` with the exception message. Firing row persisted for audit. |
| AI run failure after fire | `threads.run_ai_on_message` | Existing M4 path — `Message.status="failed"`. Visible in the thread. Separate from trigger machinery. |
| Beat tick runs longer than `TRIGGER_TICK_SECONDS` | `celery beat` | `single_instance=True` prevents overlap. Next tick skipped + logged. If chronic, indicates tick is doing too much (likely too many trigger tickers) — operational fix. |
| `fire_trigger` retries | Celery | **Not** auto-retried — `@shared_task(autoretry_for=(), max_retries=0)`. Retry would duplicate firing/snapshot/notification. |
| Cost-capped manual fire | `tasks.fire_trigger` | Same cost-capped branch as beat path. Manual fires honor the cap. |

## Observability

Structured logs via the existing `structlog` config:

- `trigger.tick` — per tick: `triggers_evaluated`, `fires_enqueued`, `duration_ms`, `tickers_fetched`.
- `trigger.tick.market_closed` — DEBUG-level; silences during off-hours.
- `trigger.fired` — per fire: `trigger_id`, `trigger_name`, `profile_id`, `matched_values`, `cost_capped`, `snapshot_id`, `thread_id`.
- `trigger.fire.capture_failed` / `trigger.fire.ai_skipped_cost_capped` — failure paths.

Redis `trigger:last_tick_at` stamps each tick; `/triggers` page displays "Last evaluated Xs ago" so the user can tell the evaluator is alive without reading logs.

## REST API

```
GET    /api/triggers/                   list triggers + firings_count + last_fired_at
POST   /api/triggers/                   create (validates DSL; 400 on invalid)
GET    /api/triggers/<id>/              retrieve
PATCH  /api/triggers/<id>/              update (DSL validation; can flip enabled)
DELETE /api/triggers/<id>/              delete (cascades TriggerFiring rows)
POST   /api/triggers/<id>/fire/         manual fire (async → 202 {task_id})
POST   /api/triggers/evaluate/          evaluator dry-run {condition|trigger_id} → {matched, values, missing}
GET    /api/triggers/<id>/firings/      paginated firing history for one trigger
GET    /api/triggers/firings/recent/    global "recent across all triggers", ?limit=5
```

Serializers expose DSL as raw JSON (frontend owns builder state). `firings_count` computed via a `.annotate(Count("firings"))` in the list queryset.

## Frontend

### Route map

```
/triggers            TriggersListPage    — list + toggle + delete + "Fire now"
/triggers/new        TriggerEditorPage   — create form (builder + live preview)
/triggers/:id        TriggerEditorPage   — edit form + "Firings" tab
```

### API client — `src/api/triggers.ts`

```typescript
export type EventTrigger = {
  id: number; name: string; profile: number;
  condition: Condition; cooldown_seconds: number;
  enabled: boolean; last_fired_at: string | null;
  firings_count: number;
  created_at: string; updated_at: string;
};

export type Firing = {
  id: number; trigger_id: number; trigger_name: string;
  fired_at: string; matched_values: Record<string, number | null>;
  snapshot_id: number | null; thread_id: number | null;
  cost_capped: boolean;
};

fetchTriggers(): Promise<EventTrigger[]>
createTrigger(body): Promise<EventTrigger>
updateTrigger(id, body): Promise<EventTrigger>
deleteTrigger(id): Promise<void>
fireTriggerNow(id): Promise<{task_id: string}>
evaluateTrigger(body: {condition} | {trigger_id}): Promise<{matched, values, missing}>
fetchFirings(triggerId, page?): Promise<{results, next, count}>
fetchRecentFirings(limit?): Promise<Firing[]>
```

### Rule builder (`TriggerEditorPage` + `RuleBuilder.tsx`)

Layout sketch:

```
Name     [SPY breakout_________________]
Profile  (Default ▾)                           Enabled [✓]
Cooldown 30 min (▾)                            Market-hours only [✓ fixed]

Fire when  (all ▾)  of:
  ┌──────────────────────────────────────────── ✕
  │ (price ▾) (SPY) (> ▾) (550)
  │ price of SPY is greater than 550
  └────────────────────────────────────────────
  ┌──────────────────────────────────────────── ✕
  │ (pct_change ▾) (SPY) (>= ▾) (0.01) (5m ▾)
  │ SPY moved ≥1% over 5m
  └────────────────────────────────────────────
  + Add condition

Preview: "would currently fire"  [ Evaluate ]  → YES · SPY=551.20
[ Save ] [ Cancel ]                                  [ Fire now ]
```

Components:
- `RuleBuilder` — owns the in-flight DSL state; exposes `{condition, valid}` to the page.
- `LeafRow` — controls for one leaf. Metric-aware: VIX and `position_*` hide ticker input; only `pct_change` shows `window`.
- `GroupDropdown` — top-level `all|any` select. `not` not exposed in UI.
- `describeLeaf(node) → string` — pure function in `src/lib/triggers/describe.ts`; unit-tested for 5 metrics × 7 ops.
- `Preview` — debounced (600ms) POST to `/api/triggers/evaluate/`; renders YES/NO + the `matched_values` dict. Red banner if backend rejects the DSL.

### Triggers list page (`TriggersListPage.tsx`)

Table columns: name · profile · condition-summary · `last_fired_at` · `firings_count` · enabled-toggle · actions (Fire now, Edit, Delete).

Condition-summary string comes from a pure `describeCondition(node) → string` in `src/lib/triggers/describe.ts`, e.g. `"SPY > 550 AND SPY ±1% /5m"`. Toggling `enabled` does an optimistic PATCH with rollback on error. "Fire now" opens a confirm dialog (explicit side-effect: snapshot + AI cost).

### Firings drill-down (tab on `/triggers/:id`)

Tabs: `Condition | Firings (N)`. Firings tab is a paginated table: `fired_at · matched_values · snapshot_link · thread_link · cost_capped?`. `cost_capped` rows get a yellow badge; firings with `thread=null` get a gray "no thread" badge.

### Dashboard widget (`RecentTriggersCard.tsx`)

Card on `/` (Dashboard), positioned near existing threads/watchlist widgets. Renders last 5 firings via `useQuery(['recent-firings'], fetchRecentFirings, {refetchInterval: 30_000})`. Empty state: card not rendered when 0 firings today. Row format:

```
SPY breakout · 10:42 · SPY=551.20        → thread
VIX spike    · 09:58 · vix=22.10         → thread
NVDA -2%     · 09:31 · pct_change=-0.024 → cost-capped
(view all →)
```

### Notifications integration

Nothing new on the frontend. `NotificationBell` (M6) already handles `kind="trigger"` and `kind="cost_limit"` rows; they land on the existing `user.anonymous.notifications` channel. OS desktop notifications fire via the permission prompt already shipped in M6.

## Testing

### Unit

- `test_evaluator.py` — parametrized over every (metric × op) combination × edge cases (missing metric → False, empty `all` → True, empty `any` → False, `not` flipping, crosses with `_prior=None`).
- `test_dsl_validation.py` — parametrized invalid shapes (unknown metric, window on non-`pct_change`, missing ticker on `price`, nested-not, wrong types) → expected error paths.
- `test_metrics.py` — `fetch_quotes` / `fetch_positions` mocked at their module boundaries; feed a list of mock `EventTrigger` instances, assert snapshot keys and Redis side effects (`fakeredis`).
- `test_cooldown.py` — `fakeredis` + `freezegun` for time math. Covers: just-fired blocks, time-elapsed-but-not-rearmed blocks, time-elapsed-and-rearmed passes.
- `test_describe.py` (frontend, vitest) — `describeLeaf` + `describeCondition` snapshot-style table.

### Integration

- `test_evaluate_triggers_task.py` — Celery eager, fakeredis, Schwab mocked. Creates 3 triggers, runs task once, asserts expected `fire_trigger` enqueues + logs.
- `test_fire_trigger_task.py` — Celery eager, fakeredis, Schwab mocked, AI provider mocked. Asserts: `TriggerFiring` + `Snapshot` + `Thread` + `Notification` rows persisted; WebSocket broadcast observable via `channel_layers.get_channel_layer()`.
- Cost-capped variant: same harness, `check_daily_cap` raises, assert `firing.cost_capped=True`, `thread=None`, `notify` called with `kind="cost_limit"`.
- `test_endpoints.py` — DRF APIClient. Covers the 9 endpoints above, including DSL-validation 400s and the evaluate dry-run.

### Frontend (vitest + @testing-library/react)

- `RuleBuilder.test.tsx` — build a leaf, assert emitted DSL JSON exactly matches.
- `TriggerEditorPage.test.tsx` — live-evaluate debounce behavior on a mocked endpoint; assert YES/NO banner appears after 600ms.
- `TriggersListPage.test.tsx` — list render, optimistic toggle, Fire-now confirm, delete confirm.
- `RecentTriggersCard.test.tsx` — empty state hidden, rows render with cost-capped badge.

### Out of scope for M7

- E2E Playwright smoke test (deferred to M8's full E2E pass).
- `volume_z` metric + its history store (deferred to M8 or cut entirely).

## Open items deferred to M8+

- `volume_z(window)` metric (requires volume history).
- Global cross-profile triggers (if the user ever wants one rule firing for multiple profiles).
- Webhook / Slack / email notification sinks.
- `/triggers/firings/` cross-trigger timeline page with filters.
- E2E Playwright test covering trigger fire → dashboard widget → thread auto-open.
- Migration to named users — replace `user.anonymous.notifications` with `user.<id>.notifications` once auth lands.

## Milestone completion criteria

- All unit + integration tests green (`make test`).
- `make lint` clean (ruff + mypy + eslint + tsc).
- Beat container running; `/triggers` page visible and usable.
- One working end-to-end fire: create a trigger ("SPY > <current + 1>"), wait one tick-beat cycle in market hours, see `TriggerFiring` row, `Thread` created, `Notification` in bell, OS desktop notification (if permitted), AI response streaming in the auto-created thread.
- Cost-cap path verified manually (set cap to $0.00, fire manually, observe `cost_capped=True` + `kind="cost_limit"` notification).
- Tagged `m7-event-triggers`.
