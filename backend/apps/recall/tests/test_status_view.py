"""GET /api/recall/status/ computes per-kind counts in a single GROUP BY query
instead of one COUNT round-trip per kind plus a total."""

from __future__ import annotations

import pytest

from apps.recall.models import RecallDocument


@pytest.fixture(autouse=True)
def _stub_embed(monkeypatch):
    # mode() calls embed(["probe"]) — stub it so the test never loads the embedding
    # model (no DB query either way; keeps the test fast and hermetic).
    monkeypatch.setattr("apps.recall.services.search.embed", lambda texts: [[0.0] * 384])


@pytest.mark.django_db
def test_recall_status_uses_single_count_query(client, django_assert_max_num_queries):
    RecallDocument.objects.create(kind="thesis", object_id=1, text="a", content_hash="h1")
    RecallDocument.objects.create(kind="thesis", object_id=2, text="b", content_hash="h2")
    RecallDocument.objects.create(kind="snapshot", object_id=1, text="c", content_hash="h3")

    with django_assert_max_num_queries(2):
        resp = client.get("/api/recall/status/")

    assert resp.status_code == 200
    counts = resp.json()["counts"]
    assert counts["thesis"] == 2
    assert counts["snapshot"] == 1
    assert counts["total"] == 3
    # every declared kind is present (zero-filled), not just the ones with rows
    for kind, _label in RecallDocument.KIND_CHOICES:
        assert kind in counts
