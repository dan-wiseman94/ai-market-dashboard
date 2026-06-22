"""The strategy-domain billable AI tasks must be at-most-once (acks_late=False).

Each of these bills a provider SYNCHRONOUSLY and is NOT idempotent (no
compare-and-set claim):

- ``warroom.run_debate`` — N personas x rounds + a synthesis call, the most
  expensive AI path in the app; ends by posting an *unconditional*
  ``warroom_verdict`` Message.
- ``coverage.revise_from_observation`` — a ``run_structured`` house-view revision.
- ``strategy.regime_refresh`` — a ``run_structured`` narrative plus an
  *unconditional* ``RegimeReading.objects.create()`` append (no unique key).

They inherit the GLOBAL ``task_acks_late=True`` / ``task_reject_on_worker_lost=True``
from ``config.celery``. Before this guard, a worker killed mid-task (OOM, the 660s
``task_time_limit`` SIGKILL on a deep grounded debate, or the routine
``docker compose restart worker``) would redeliver and re-run the entire
workload — re-billing every persona, posting a SECOND contradictory verdict, and
appending a duplicate ``RegimeReading`` row. At-most-once makes a lost run a
retriable incomplete result, never a silent double-charge. Mirrors
``apps/threads/tests/test_run_ai_acks.py``; locks the override so the global
default can't silently re-enable redelivery of these billing paths.
"""

from __future__ import annotations

import pytest

from apps.strategy.tasks import refresh, revise_from_observation, run_debate


@pytest.mark.parametrize(
    "task",
    [run_debate, revise_from_observation, refresh],
    ids=["warroom.run_debate", "coverage.revise_from_observation", "strategy.regime_refresh"],
)
def test_strategy_ai_tasks_are_at_most_once(task) -> None:
    assert task.acks_late is False, f"{task.name} must override the global acks_late=True"
    assert task.reject_on_worker_lost is False, (
        f"{task.name} must override the global reject_on_worker_lost=True"
    )
