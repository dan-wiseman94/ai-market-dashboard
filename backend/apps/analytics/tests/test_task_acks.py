"""The eval-harness tasks must be at-most-once (acks_late=False).

Both replay paths bill one model call per labeled row and end with an
unconditional ``EvalRun`` append — no claim, no dedup key. Under the GLOBAL
``task_acks_late=True`` / ``task_reject_on_worker_lost=True`` from
``config.celery``, a worker killed mid-replay (OOM, the 660s hard time limit on a
long replay, a routine ``docker compose restart worker``) would redeliver and
re-bill the entire run, then store a second EvalRun that the coach and the
calibration-weighted router read as an independent measurement. At-most-once makes
a lost run a missing result the user re-triggers. Mirrors
``apps/strategy/tests/test_task_acks.py``.
"""

from __future__ import annotations

import pytest

from apps.analytics.tasks import run_manual, run_scheduled


@pytest.mark.parametrize(
    "task",
    [run_scheduled, run_manual],
    ids=["analytics.aieval_run_scheduled", "analytics.aieval_run_manual"],
)
def test_eval_tasks_are_at_most_once(task) -> None:
    assert task.acks_late is False, f"{task.name} must override the global acks_late=True"
    assert task.reject_on_worker_lost is False, (
        f"{task.name} must override the global reject_on_worker_lost=True"
    )
