import pytest
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.observer.models import ObserverSchedule
from apps.observer.services.sync import delete_periodic_task, sync_periodic_task
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_sync_periodic_task_creates_on_first_call():
    p = TradingProfile.objects.create(name="P", style="x")
    s = ObserverSchedule.objects.create(name="hourly", profile=p)
    pt = sync_periodic_task(s, cron="0 * * * *")
    s.refresh_from_db()
    assert s.periodic_task_id == pt.id
    assert pt.task == "observer.run_observer"
    assert pt.enabled is True
    assert pt.crontab.minute == "0"
    assert pt.crontab.hour == "*"
    import json
    assert json.loads(pt.kwargs) == {"schedule_id": s.id}


@pytest.mark.django_db
def test_sync_periodic_task_updates_on_second_call():
    p = TradingProfile.objects.create(name="P", style="x")
    s = ObserverSchedule.objects.create(name="hourly", profile=p)
    sync_periodic_task(s, cron="0 * * * *")
    pt_id_first = s.periodic_task_id
    s.enabled = False
    s.save()
    sync_periodic_task(s, cron="*/15 * * * *")
    s.refresh_from_db()
    assert s.periodic_task_id == pt_id_first  # same row, updated
    assert s.periodic_task.crontab.minute == "*/15"
    assert s.periodic_task.enabled is False
    # No orphaned observer PeriodicTask rows (filter excludes seeded trigger-evaluator task)
    assert PeriodicTask.objects.filter(task="observer.run_observer").count() == 1


@pytest.mark.django_db
def test_delete_periodic_task_removes_periodic_task_only():
    p = TradingProfile.objects.create(name="P", style="x")
    s = ObserverSchedule.objects.create(name="hourly", profile=p)
    sync_periodic_task(s, cron="0 * * * *")
    crontab_id = s.periodic_task.crontab_id
    delete_periodic_task(s)
    s.refresh_from_db()
    assert PeriodicTask.objects.filter(task="observer.run_observer").count() == 0
    assert CrontabSchedule.objects.filter(id=crontab_id).exists()
