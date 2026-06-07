"""``observer.run_observer`` must be at-most-once (acks_late=False).

The ``structured`` and ``consensus`` observer paths call ``run_structured``
SYNCHRONOUSLY inside ``run_observer`` (only the plain path delegates to the
already-at-most-once ``run_ai_on_message.delay()``). Inheriting the global
``task_acks_late=True`` / ``task_reject_on_worker_lost=True`` from
``config.celery``, a worker killed mid-fire would redeliver and re-run the whole
fire — re-capturing the snapshot and re-billing the structured/consensus call. A
lost observer fire is covered by the next periodic fire, so at-most-once is the
correct guarantee. Mirrors ``apps/threads/tests/test_run_ai_acks.py``.
"""

from __future__ import annotations

from apps.observer.tasks import run_observer_task


def test_run_observer_is_at_most_once() -> None:
    assert run_observer_task.acks_late is False
    assert run_observer_task.reject_on_worker_lost is False
