"""``snapshots.capture`` must be at-most-once (acks_late=False).

Capture is not idempotent — sections fetch and persist with side effects and the
task carries no compare-and-set claim — so it must override the Celery app's
global task_acks_late=True. A worker killed mid-capture would otherwise redeliver
and re-run every section. This test locks the override so the global default
can't silently re-enable redelivery.
"""

from __future__ import annotations

from apps.snapshots.tasks import capture_task


def test_capture_task_does_not_redeliver_on_worker_loss():
    assert capture_task.acks_late is False
    assert capture_task.reject_on_worker_lost is False
