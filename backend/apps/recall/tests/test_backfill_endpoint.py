"""POST /api/recall/backfill/ — queue the index catch-up that was CLI-only.

No provider spend: embeddings come from the local fastembed model, so there is no
cost cap and no mock-mode hazard here. The endpoint only has to stay off the
request thread (a full backlog is thousands of embeddings) and stay idempotent.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from apps.recall import tasks as recall_tasks
from apps.recall.models import RecallDocument
from apps.thesis.models import Thesis

pytestmark = pytest.mark.django_db


def test_backfill_dispatches_async(monkeypatch):
    delay = MagicMock(return_value=MagicMock(id="task-123"))
    monkeypatch.setattr(recall_tasks.backfill, "delay", delay)

    resp = APIClient().post("/api/recall/backfill/")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    delay.assert_called_once()


def test_backfill_is_idempotent(monkeypatch):
    """A second press must queue nothing: pending() excludes what is already indexed."""
    dispatched: list[tuple[str, int]] = []
    monkeypatch.setattr(
        recall_tasks.index_document,
        "delay",
        lambda kind, oid: dispatched.append((kind, oid)),
    )
    thesis = Thesis.objects.create(
        title="t", ticker="AAPL", direction="bullish", rationale="r", invalidation_note="n"
    )

    first = recall_tasks.backfill()
    assert ("thesis", thesis.id) in dispatched
    assert first["dispatched"] == len(dispatched)

    # Simulate the dispatched index task landing, then press again.
    RecallDocument.objects.create(kind="thesis", object_id=thesis.id, text="t", content_hash="h")
    dispatched.clear()

    assert recall_tasks.backfill()["dispatched"] == 0
    assert dispatched == []
