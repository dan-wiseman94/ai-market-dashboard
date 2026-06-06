"""``run_ai_on_message`` must be at-most-once (acks_late=False).

It is the one hot-path task that bills a provider AND streams to the user, and it
is NOT idempotent: each run creates a fresh assistant Message + AIRun with no
compare-and-set claim. The Celery app sets a GLOBAL ``task_acks_late=True`` +
``task_reject_on_worker_lost=True`` (correct for the idempotent background tasks
that each carry their own claim/lock). Inherited by this task, a worker killed
mid-stream (OOM, time-limit, deploy) would redeliver it and re-bill + re-stream a
duplicate assistant message.

At-most-once is the correct delivery guarantee for a billing+streaming task: a
run lost to a crash shows the user an incomplete stream they can retry, never a
silent double-charge. This test locks that in so the global default can't
silently re-enable redelivery of this task.
"""

from __future__ import annotations

from apps.threads.tasks import run_ai_on_message


def test_run_ai_on_message_does_not_redeliver_on_worker_loss():
    assert run_ai_on_message.acks_late is False
    assert run_ai_on_message.reject_on_worker_lost is False
