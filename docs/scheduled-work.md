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

Two scheduled tasks can incur real AI/$ cost on their own — both ship **gated OFF**:

| Task | Cadence | Gate (must be ON) |
|---|---|---|
| `strategy.sweep` | every 30 min | `ANOMALY_SWEEP_ENABLED` |
| `analytics.aieval_run_scheduled` | weekly Mon 05:00 | `AIEVAL_SCHEDULED_ENABLED` |

The drift gate's `test_gated_spending_tasks_name_a_real_flag` enforces that any
`spends=True` task names a real feature flag — autonomous spend is never always-on.
(Analysis tasks like post-mortems / regime / book may call the model, but only under
their own per-provider cost caps; see CLAUDE.md → "Cost caps".)

## Cadence at a glance

- **Every minute:** `market.refresh_schwab_token`, `observer.fire_close_relative_schedules`
- **Sub-5-min:** `observer.poll_open_batches` (60s)
- **Every 5 min:** `recall.index_pending`, `thesis.run_due_postmortems`,
  `observer.resolve_due_predictions`, `observer.check_prediction_invalidations`
- **Every 15–30 min:** `observer.briefing_run_scheduled` (fires once/day), `strategy.regime_refresh`
  (market-hours guard inside), `strategy.sweep` *(gated)*
- **Daily:** `market.refresh_corporate_actions` (08:30), `market.refresh_events` (09:00),
  `market.ingest_daily_bars` (22:30), `book.snapshot_daily` (22:45),
  `core.prune_retention` (04:00 UTC), `thesis.distill` (05:30),
  `analytics.calibration_drift_sentinel` (06:00)
- **Weekly:** `analytics.aieval_run_scheduled` (Mon 05:00) *(gated)*, `backups.verify_latest`
  (Sun 05:00 — restore-drill: `pg_restore --list` the newest backup, critical ErrorEvent on failure)

See the registry for the per-task summary and owner. Note `beat` does not hot-reload —
after editing the schedule, `docker compose restart worker beat` (CLAUDE.md → Docker).
