"""Tests that the Celery app is configured with production-hardening defaults.

These assert actual app.conf values so any future regression in celery.py is
caught immediately — before a worker ever boots.
"""

from config.celery import app

from apps.backups.tasks import run_backup


def test_celery_hardening_config():
    assert app.conf.task_soft_time_limit == 600
    assert app.conf.task_time_limit == 660
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_max_tasks_per_child == 200
    assert app.conf.result_expires == 3600


def test_backup_task_has_extended_time_limits():
    """pg_dump allows up to 30 min (subprocess timeout=1800); the Celery task
    wrapper must carry a matching per-task override so the global 660s hard
    limit does not kill a legitimately long backup.
    """
    assert run_backup.soft_time_limit == 1800
    assert run_backup.time_limit == 1860
