"""Thread create must not run network-bound assembly inside transaction.atomic().

serialize_for_ai token-counts via the provider API (per-section HTTPS calls) and
assemble_coach_context runs embedding inference; holding an open Postgres
transaction across those round trips leaves an idle-in-transaction connection for
as long as the external API takes. Only the Thread + synthetic Message writes
need atomicity.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Message


# transaction=True: the regular django_db mark wraps the whole test in an atomic
# block, which would make in_atomic_block True regardless of the view's scoping.
@pytest.mark.django_db(transaction=True)
def test_pinned_snapshot_assembly_runs_outside_the_atomic_block():
    profile = TradingProfile.objects.create(name="P", style="x", enable_coach=False)
    snap = Snapshot.objects.create(
        profile=profile, objective="o", status="ready", includes=["quotes"], source="manual"
    )

    seen: dict[str, bool] = {}

    def fake_serialize(s, **kwargs):
        seen["serialize_in_atomic"] = connection.in_atomic_block
        return "PAYLOAD"

    def fake_coach(s, p):
        seen["coach_in_atomic"] = connection.in_atomic_block
        return "COACH "

    with (
        patch("apps.threads.views.serialize_for_ai", side_effect=fake_serialize),
        patch("apps.threads.views.assemble_coach_context", side_effect=fake_coach),
    ):
        resp = APIClient().post(
            "/api/threads/",
            data={
                "kind": "consult",
                "profile_id": profile.id,
                "pinned_snapshot_id": snap.id,
                "title": "t",
            },
            format="json",
        )

    assert resp.status_code == 201
    assert seen == {"serialize_in_atomic": False, "coach_in_atomic": False}
    msg = Message.objects.get(thread_id=resp.json()["id"], role="user")
    assert msg.content["text"] == "COACH PAYLOAD"
    assert msg.snapshot_ref_id == snap.id
