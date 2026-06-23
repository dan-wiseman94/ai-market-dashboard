"""Authoritative inventory of the project's scheduled (Celery beat) work.

19 beat entries across a dozen apps is a second, invisible execution model: nothing
in a request path reveals what runs at 3am, how often, or whether it spends money.
This registry makes that surface legible — every `app.conf.beat_schedule` task gets a
cadence, owner, one-line summary, and (crucially) its **gate**: the feature flag that
must be on for it to do anything, or "" for always-on.

A drift gate (`apps/core/tests/test_scheduled_work_inventory.py`) asserts this set
equals the live `beat_schedule`, so a new scheduled task with no entry here — or an
entry whose task was removed — fails CI. Same philosophy as the OpenAPI/feature-flag
drift gates. See docs/scheduled-work.md for the narrative.

`spends` flags tasks that can incur real AI/$ cost autonomously — the rows worth the
most scrutiny. (Many "analysis" tasks call the model only via their own cost caps; the
two `spends=True` rows are the ones gated OFF by default.)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledTask:
    task: str  # the Celery task name, matching beat_schedule[*]["task"]
    cadence: str  # human-readable schedule
    summary: str  # what it does
    gate: str  # feature flag that must be ON, or "" for always-on
    spends: bool = False  # can it incur AI/$ cost autonomously?


SCHEDULED_WORK: list[ScheduledTask] = [
    # --- frequent maintenance / freshness ---
    ScheduledTask(
        "market.refresh_schwab_token",
        "every minute",
        "Refresh the Schwab OAuth access token before expiry.",
        "",
    ),
    ScheduledTask(
        "observer.fire_close_relative_schedules",
        "every minute",
        "Fire observer schedules defined relative to the market close (once/day guard inside).",
        "",
    ),
    ScheduledTask(
        "observer.poll_open_batches",
        "every 60s",
        "Move completed Anthropic Messages-batch observations in.",
        "",
    ),
    ScheduledTask(
        "recall.index_pending",
        "every 5 min",
        "Embed + index documents pending semantic-recall indexing.",
        "",
    ),
    ScheduledTask(
        "thesis.run_due_postmortems",
        "every 5 min",
        "Run post-mortems whose horizon has elapsed (idempotent scheduled→running claim).",
        "",
    ),
    ScheduledTask(
        "observer.resolve_due_predictions",
        "every 5 min",
        "Resolve AI predictions whose horizon has elapsed.",
        "",
    ),
    ScheduledTask(
        "observer.check_prediction_invalidations",
        "every 5 min",
        "Invalidate open predictions whose invalidation level was breached.",
        "",
    ),
    ScheduledTask(
        "strategy.regime_refresh",
        "every 30 min + forced ~09:00 ET",
        "Append a market-regime reading (intraday market-hours guard inside).",
        "",
    ),
    ScheduledTask(
        "strategy.sweep",
        "every 30 min",
        "Agentic anomaly sweep that auto-originates DeskEntry investigations.",
        "ANOMALY_SWEEP_ENABLED",
        spends=True,
    ),
    ScheduledTask(
        "observer.briefing_run_scheduled",
        "every 15 min (fires once/day)",
        "Assemble + AI-synthesise the Morning Briefing (unique scheduled_date claim).",
        "",
    ),
    # --- daily batch / end-of-day ---
    ScheduledTask(
        "market.refresh_corporate_actions",
        "daily 08:30",
        "Refresh splits/dividends used by the returns math.",
        "",
    ),
    ScheduledTask(
        "market.refresh_events", "daily 09:00", "Refresh the forward earnings + macro calendar.", ""
    ),
    ScheduledTask(
        "market.ingest_daily_bars",
        "daily 22:30",
        "Ingest the day's OHLC bars for stored-price analytics.",
        "",
    ),
    ScheduledTask(
        "book.snapshot_daily",
        "daily 22:45",
        "Append the whole-book risk reading (after bar ingest).",
        "",
    ),
    ScheduledTask(
        "core.prune_retention",
        "daily 04:00 UTC",
        "Prune data past its retention window (low-traffic window).",
        "",
    ),
    ScheduledTask(
        "thesis.distill",
        "daily 05:30",
        "Cluster recurring post-mortem lessons (deterministic embeddings, no AI call).",
        "",
    ),
    # --- weekly, real spend, default OFF ---
    ScheduledTask(
        "analytics.aieval_run_scheduled",
        "weekly Mon 05:00",
        "Replay the calibration eval against frozen snapshots — hits the real model.",
        "AIEVAL_SCHEDULED_ENABLED",
        spends=True,
    ),
    ScheduledTask(
        "analytics.calibration_drift_sentinel",
        "daily 06:00",
        "Notify when a model's calibration_error drifts (reads EvalRuns; no AI call).",
        "CALIBRATION_DRIFT_SENTINEL_ENABLED",
    ),
]


def task_names() -> set[str]:
    """Distinct scheduled task names — the canonical side of the drift gate."""
    return {t.task for t in SCHEDULED_WORK}
