import pytest

from apps.profiles.models import TradingProfile
from apps.recall.models import RecallDocument
from apps.recall.services.index import index_one, pending
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
