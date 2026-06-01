import pytest

from apps.desk.models import DeskEntry
from apps.threads.models import Thread

pytestmark = pytest.mark.django_db


def test_investigation_thread_fk():
    th = Thread.objects.create(kind="consult", title="Investigate NVDA")
    e = DeskEntry.objects.create(
        anomaly_type="price_move", ticker="NVDA", severity=9.0, investigation_thread=th
    )
    assert e.investigation_thread_id == th.id
