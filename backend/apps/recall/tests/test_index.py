import pytest

from apps.profiles.models import TradingProfile
from apps.recall.models import RecallDocument
from apps.recall.services.index import index_one, pending, reconcile
from apps.thesis.models import Thesis


@pytest.mark.django_db
def test_index_one_upserts(monkeypatch):
    import apps.recall.services.index as idx

    monkeypatch.setattr(idx, "embed", lambda texts: [[0.0] * 384 for _ in texts])
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    index_one("thesis", th.id)
    doc = RecallDocument.objects.get(kind="thesis", object_id=th.id)
    assert doc.tickers == ["NVDA"] and doc.embedding is not None


@pytest.mark.django_db
def test_index_one_null_embedding_when_no_backend(monkeypatch):
    import apps.recall.services.index as idx

    monkeypatch.setattr(idx, "embed", lambda texts: None)
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    index_one("thesis", th.id)
    assert RecallDocument.objects.get(kind="thesis", object_id=th.id).embedding is None


@pytest.mark.django_db
def test_pending_finds_unindexed():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    assert ("thesis", th.id) in list(pending(cap=50))


@pytest.mark.django_db
def test_pending_excludes_already_indexed_at_db():
    """A source already present in RecallDocument is excluded — no rescan churn."""
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    RecallDocument.objects.create(kind="thesis", object_id=th.id, text="x", content_hash="h")
    assert ("thesis", th.id) not in pending(cap=50)


@pytest.mark.django_db
def test_pending_returns_newest_first_and_respects_cap():
    """Under a backlog larger than cap, the most-recent rows are picked first so the
    cap meaningfully bounds the scan (and recent items become searchable soonest)."""
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    ths = [
        Thesis.objects.create(title=f"t{i}", ticker="NVDA", direction="bullish", profile=p)
        for i in range(3)
    ]
    result = pending(cap=2)
    thesis_ids = [oid for kind, oid in result if kind == "thesis"]
    assert thesis_ids == [ths[2].id, ths[1].id]


@pytest.mark.django_db
def test_reconcile_deletes_orphaned_recall_docs():
    """RecallDocument keys its source as a generic (kind, object_id) pair with NO FK, so a
    deleted source leaves a stale row that keeps scoring in semantic + keyword recall (the
    Coach can then quote a since-deleted object). The index path only adds/updates;
    reconcile() drops rows whose source no longer resolves. A live source is kept."""
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    live = RecallDocument.objects.create(
        kind="thesis", object_id=th.id, text="x", content_hash="h1"
    )
    orphan_thesis = RecallDocument.objects.create(
        kind="thesis", object_id=th.id + 9999, text="y", content_hash="h2"
    )
    orphan_message = RecallDocument.objects.create(
        kind="message", object_id=987654, text="z", content_hash="h3"
    )

    deleted = reconcile()

    assert deleted == 2
    assert RecallDocument.objects.filter(pk=live.pk).exists()
    assert not RecallDocument.objects.filter(pk=orphan_thesis.pk).exists()
    assert not RecallDocument.objects.filter(pk=orphan_message.pk).exists()


@pytest.mark.django_db
def test_reconcile_removes_doc_after_source_deleted():
    """End-to-end: deleting the source then reconciling removes its recall row."""
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    RecallDocument.objects.create(kind="thesis", object_id=th.id, text="x", content_hash="h")
    th.delete()
    assert reconcile() == 1
    assert RecallDocument.objects.count() == 0
