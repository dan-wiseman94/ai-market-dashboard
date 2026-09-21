# Scheduled work (Celery beat)

A living inventory of everything that runs on a schedule — the `app.conf.beat_schedule`
entries in `backend/config/celery.py`.

**Authoritative, machine-checked list:** [`backend/apps/core/scheduled_tasks.py`](../backend/apps/core/scheduled_tasks.py).
A drift gate (`backend/apps/core/tests/test_scheduled_work_inventory.py`) fails CI if a
beat task is added without a `SCHEDULED_WORK` entry, or an entry outlives its task. This
page is the human narrative; the registry is the source of truth.

## Why this exists

Scheduled work is a second, invisible execution model: nothing in a request path tells
you what runs at 3am, how often, or whether it spends money autonomously. The registry
makes that surface legible and the gate keeps it honest. Pair it with
`test_celery_registration.py`, which separately guarantees every scheduled task name
actually resolves to a registered Celery task (the documented autodiscovery landmine).

## What spends money

Two scheduled tasks can originate AI/$ cost on their own. Both are armed by default and
both are switchable from **Settings → Features → Autonomous spend**:

| Task | Cadence | Switch | Default |
|---|---|---|---|
| `strategy.sweep` | every 30 min | `ANOMALY_SWEEP_ENABLED` | ON |
| `analytics.aieval_run_scheduled` | weekly Mon 05:00 | `AIEVAL_SCHEDULED_ENABLED` | ON |

Three things bound them. The **autonomous daily cap**
(`AI_AUTONOMOUS_DAILY_CAP_USD`, $5.00 by default, on the same page) is the ceiling on
everything nobody asked for; the **per-provider daily and monthly caps** apply on top;
and each task **refuses under `MOCK_EXTERNAL`** before doing any work, so an armed
schedule in the e2e overlay stops at the task boundary rather than deep inside a
replay. (`run_structured` returns a canned instance under `MOCK_EXTERNAL` as well, so
the billable call is blocked twice.)

The drift gate's `test_gated_spending_tasks_name_a_real_flag` enforces that any
`spends=True` task names a real feature flag — autonomous spend stays switchable rather
than becoming unconditional. (Analysis tasks like post-mortems / regime / book may call
the model, but only under their own per-provider cost caps; see CLAUDE.md → "Cost
caps".)

One further task carries a switch without spending anything:
`analytics.calibration_drift_sentinel` (`CALIBRATION_DRIFT_SENTINEL_ENABLED`, ON) reads
stored `EvalRun`s and calls no model. Every other scheduled task runs unconditionally.

## Cadence at a glance

19 tasks across 20 beat entries (`strategy.regime_refresh` has two: an intraday one and
a forced pre-open one).

- **Every minute:** `market.refresh_schwab_token`, `observer.fire_close_relative_schedules`
- **Sub-5-min:** `observer.poll_open_batches` (60s)
- **Every 5 min:** `recall.index_pending`, `thesis.run_due_postmortems`,
  `observer.resolve_due_predictions`, `observer.check_prediction_invalidations`
- **Every 15–30 min:** `observer.briefing_run_scheduled` (fires once/day), `strategy.regime_refresh`
  (market-hours guard inside), `strategy.sweep` *(switchable; spends)*
- **Daily:** `market.refresh_corporate_actions` (08:30), `market.refresh_events` (09:00),
  `market.ingest_daily_bars` (22:30), `book.snapshot_daily` (22:45),
  `core.prune_retention` (04:00 UTC), `thesis.distill` (05:30),
  `analytics.calibration_drift_sentinel` (06:00 — *switchable; no AI $*)
- **Weekly:** `analytics.aieval_run_scheduled` (Mon 05:00 — *switchable; spends*), `backups.verify_latest`
  (Sun 05:00 — restore-drill: `pg_restore --list` the newest backup, critical ErrorEvent on failure)

Retention windows for what these tasks write (`core.prune_retention`) are switches too;
[`toggles.md`](toggles.md) lists them with their defaults.

See the registry for the per-task summary and owner. Note `beat` does not hot-reload —
after editing the schedule, `docker compose restart worker beat` (CLAUDE.md → Docker).
