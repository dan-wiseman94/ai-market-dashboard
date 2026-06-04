"""Drift gate: the scheduled-work inventory mirrors the live Celery beat schedule.

Complexity lever (CLAUDE.md): 19 beat entries across a dozen apps are an invisible
second execution model. This keeps the inventory honest — a beat task added without a
`SCHEDULED_WORK` entry (undocumented), or an entry whose task was removed (stale), turns
red. Mirrors the OpenAPI/feature-flag drift gates for scheduled work.

Both sides are live code (config.celery.beat_schedule + apps.core.scheduled_tasks), so
there's no baked-doc staleness — the gate always reads the running definitions.
"""

from config.celery import app

from apps.core.scheduled_tasks import SCHEDULED_WORK, task_names


def _beat_task_names() -> set[str]:
    return {entry["task"] for entry in app.conf.beat_schedule.values()}


def test_inventory_exactly_mirrors_beat_schedule():
    in_beat = _beat_task_names()
    in_inventory = task_names()

    undocumented = in_beat - in_inventory
    stale = in_inventory - in_beat

    assert not undocumented, (
        f"beat task(s) with no SCHEDULED_WORK entry: {sorted(undocumented)} — "
        "add them to apps/core/scheduled_tasks.py (and docs/scheduled-work.md)"
    )
    assert not stale, (
        f"SCHEDULED_WORK entr(ies) whose beat task no longer exists: {sorted(stale)} — "
        "remove the stale inventory entry"
    )


def test_gated_spending_tasks_name_a_real_flag():
    """Every task marked spends=True must be gated by a feature flag — autonomous
    money-spending on a schedule must be opt-in, never always-on."""
    from apps.core.feature_flags import flag_names

    flags = flag_names()
    for t in SCHEDULED_WORK:
        if t.spends:
            assert t.gate, f"{t.task!r} spends $ but has no gate flag"
            assert t.gate in flags, (
                f"{t.task!r} names gate {t.gate!r}, which is not a registered feature flag"
            )
