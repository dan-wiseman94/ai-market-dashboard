# Calibration-Drift Sentinel — Design

**Written 2026-06-22.** Feature #14. Watch the AI's calibration over time; alert
when a model drifts from well-calibrated to over/under-confident. Reuses the
`EvalRun` series (the eval harness output) + the `notify` + opt-in-beat patterns.

## Decisions (brainstormed)
- **Data source:** trend `EvalRun.calibration_error` (the explicit calibration time
  series). v1 is EvalRun-only — honest `insufficient_history` when the opt-in eval
  harness hasn't run. Live rolling-window recompute deferred (YAGNI).
- **Alert:** opt-in daily beat task, fires only on a stable→drifting transition
  (dedup'd once/day per model). Default OFF (it's autonomy that notifies).

## 1. Analytics — `apps/analytics/services/calibration_drift.py`
`calibration_drift(*, window_days=30, min_runs=3) -> dict` — for each `model`:
- `recent` = EvalRuns with `created_at >= now-window_days`; `baseline` = the
  `window_days` immediately before that. Use `calibration_error` (lower = better),
  averaged per window (ignoring None).
- `drifting = recent_err is not None and baseline_err is not None and
  recent_err - baseline_err >= 0.05 and recent_err >= baseline_err * 1.5`
  (worsened by ≥0.05 absolute AND ≥50% relative — both, to avoid noise).
- `direction`: from the most-recent run's `avg_confidence` vs `hit_rate` —
  `overconfident` when confidence > hit_rate by >0.05, `underconfident` when <−0.05,
  else `stable`.
- Min-runs gate: a window with < `min_runs` scored runs → that model is
  `status="insufficient_history"` (never a drift verdict on thin data).
- Returns `{generated_at, window_days, models: [{model, recent_error, baseline_error,
  delta, drifting, direction, status, recent_runs, baseline_runs}]}`.

Pure read; one indexed query (`EvalRun.objects.filter(created_at__gte=...).values(...)`),
aggregated in memory. An N+1 budget test pins the query count.

## 2. Sentinel — opt-in beat task
`@shared_task(name="analytics.calibration_drift_sentinel")` (acks_late inherited is
fine — `notify` + a Redis dedup marker make it idempotent). Gated on
`env.bool("CALIBRATION_DRIFT_SENTINEL_ENABLED", default=False)` — registered in
`apps/core/feature_flags.py`; the beat entry registered in
`apps/core/scheduled_tasks.py` (drift-gated). Daily cadence.

Logic: run `calibration_drift()`; for each model now `drifting` whose Redis marker
`caldrift:fired:<model>` is unset, `notify(user_id=None, kind="calibration_drift",
title="Calibration drift: <model>", body="<model> looks <direction> — calibration
error <baseline>→<recent>", link="/scorecard")` and `SETEX` the marker for 24h.
Models that recover (not drifting) `DELETE` their marker so a future drift re-alerts.

## 3. Readout
- `GET /api/analytics/calibration-drift/` → the `calibration_drift()` dict (DRF
  function view under the existing analytics routes).
- Scorecard: a compact "Calibration drift" line per drifting model
  (`<model>: overconfident, error 0.08→0.16`), hidden when none drift.

## 4. Testing
- `calibration_drift`: hand-checkable drift (baseline 0.05 → recent 0.20 = drifting),
  no-drift (stable), min-runs gate (`insufficient_history`), direction classification.
- Sentinel: fires once on transition, dedup (second run no-op), recovery clears the
  marker, disabled-flag no-op. `CELERY_TASK_ALWAYS_EAGER` + fakeredis.
- API: 200 shape; query-budget test.
- FE: scorecard shows the drift line when present; vitest.

## Out of scope (YAGNI)
Live rolling-window recompute from predictions, per-provider (vs per-model)
breakdown, configurable thresholds in the UI, drift on Brier (calibration_error is
the direct signal).
