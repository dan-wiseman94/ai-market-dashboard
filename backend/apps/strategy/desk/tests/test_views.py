import pytest
from rest_framework.test import APIClient

from apps.strategy.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_list_feed():
    DeskEntry.objects.create(anomaly_type="price_move", ticker="NVDA", severity=9.0, finding="f")
    rows = APIClient().get("/api/desk/").json()
    assert len(rows) == 1 and rows[0]["ticker"] == "NVDA"


def test_manual_sweep(monkeypatch):
    from apps.strategy.desk import views

    monkeypatch.setattr(views, "run_sweep", lambda **k: 3)
    resp = APIClient().post("/api/desk/sweep/")
    assert resp.status_code == 200 and resp.json()["created"] == 3


def test_dismiss():
    e = DeskEntry.objects.create(anomaly_type="x", ticker="Y", severity=1.0)
    resp = APIClient().post(f"/api/desk/{e.id}/dismiss/")
    assert resp.status_code == 200
    e.refresh_from_db()
    assert e.status == "dismissed"


def test_act_convenes_warroom(monkeypatch):
    from apps.strategy.desk import views
    from apps.strategy.models import WarRoomRun
    from apps.threads.models import Thread

    e = DeskEntry.objects.create(
        anomaly_type="price_move",
        ticker="NVDA",
        severity=9.0,
        finding="big move",
        suggested_actions=[
            {
                "type": "convene_warroom",
                "label": "Convene",
                "params": {"free_prompt": "Debate: big move"},
            }
        ],
    )

    def _fake_convene(**kwargs):
        th = Thread.objects.create(kind="warroom", title="t")
        return WarRoomRun.objects.create(
            thread=th, subject_kind="free", subject_label="x", confidence=0.5
        )

    monkeypatch.setattr(views, "convene", _fake_convene)
    resp = APIClient().post(f"/api/desk/{e.id}/act/", {"action": "convene_warroom"}, format="json")
    assert resp.status_code == 200
    e.refresh_from_db()
    assert e.status == "acted" and e.warroom_run_id is not None
