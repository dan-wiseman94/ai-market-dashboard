import pytest
from rest_framework.test import APIClient

from apps.desk.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_serializer_exposes_investigation_thread():
    from apps.threads.models import Thread

    th = Thread.objects.create(kind="consult", title="t")
    e = DeskEntry.objects.create(anomaly_type="x", ticker="NVDA", severity=1.0, investigation_thread=th)
    body = APIClient().get(f"/api/desk/{e.id}/").json()
    assert body["investigation_thread_id"] == th.id


def test_act_revise_coverage(monkeypatch):
    from apps.desk import views

    e = DeskEntry.objects.create(anomaly_type="coverage_stale", ticker="NVDA", severity=8.0, finding="stale",
                                 suggested_actions=[{"type": "revise_coverage", "label": "Revise", "params": {"ticker": "NVDA"}}])
    called = {}
    monkeypatch.setattr(views, "_revise_coverage_action", lambda ticker: called.setdefault("t", ticker) or True)
    resp = APIClient().post(f"/api/desk/{e.id}/act/", {"action": "revise_coverage"}, format="json")
    assert resp.status_code == 200
    assert called["t"] == "NVDA"
    e.refresh_from_db()
    assert e.status == "acted"
