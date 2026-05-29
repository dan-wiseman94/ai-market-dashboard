from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import Message, Thread


def _snap(p, last):
    s = Snapshot.objects.create(
        profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    SnapshotSection.objects.create(
        snapshot=s, kind="quotes", status="done", payload={"NVDA": {"last": last}}
    )
    return s


@pytest.mark.django_db
def test_explain_diff_creates_thread_and_dispatches():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    a, b = _snap(p, 100), _snap(p, 110)  # noqa: F841 — a creates the prior snapshot in the DB
    with patch("apps.snapshots.views.run_ai_on_message") as run:
        r = APIClient().post(f"/api/snapshots/{b.id}/explain-diff/", {}, format="json")
    assert r.status_code in (200, 201)
    body = r.json()
    assert "thread_id" in body and "delta" in body
    th = Thread.objects.get(id=body["thread_id"])
    assert th.kind == "diff" and th.pinned_snapshot_id == b.id
    msg = Message.objects.get(id=body["message_id"])
    assert msg.role == "user" and msg.status == "done" and msg.snapshot_ref_id == b.id
    run.delay.assert_called_once()


@pytest.mark.django_db
def test_explain_diff_no_prior_400():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    only = _snap(p, 100)
    r = APIClient().post(f"/api/snapshots/{only.id}/explain-diff/", {}, format="json")
    assert r.status_code == 400 and r.json()["code"] == "no_prior"
