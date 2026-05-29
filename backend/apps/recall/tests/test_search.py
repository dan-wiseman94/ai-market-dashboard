import pytest

from apps.recall.models import RecallDocument
from apps.recall.services import search as S


def _doc(oid, vec, text="hello", ticker="NVDA"):
    return RecallDocument.objects.create(
        kind="thesis",
        object_id=oid,
        text=text,
        embedding=vec,
        embedding_model="m",
        tickers=[ticker],
        content_hash=str(oid),
    )


@pytest.mark.django_db
def test_semantic_search_orders_by_cosine(monkeypatch):
    near = [1.0] + [0.0] * 383
    far = [0.0] * 383 + [1.0]
    a = _doc(1, near)
    b = _doc(2, far)  # noqa: F841
    monkeypatch.setattr(S, "embed", lambda texts: [near])
    hits = S.search("q", k=2)
    assert hits[0]["object_id"] == a.id


@pytest.mark.django_db
def test_fts_fallback_when_no_embedding(monkeypatch):
    from django.contrib.postgres.search import SearchVector

    d = _doc(1, None, text="nvidia earnings beat")
    RecallDocument.objects.filter(pk=d.pk).update(search=SearchVector("text"))
    monkeypatch.setattr(S, "embed", lambda texts: None)
    hits = S.search("earnings", k=5)
    assert any(h["object_id"] == d.object_id for h in hits)


@pytest.mark.django_db
def test_ticker_filter(monkeypatch):
    monkeypatch.setattr(S, "embed", lambda texts: [[1.0] + [0.0] * 383])
    _doc(1, [1.0] + [0.0] * 383, ticker="NVDA")
    _doc(2, [1.0] + [0.0] * 383, ticker="SPY")
    assert {h["object_id"] for h in S.search("q", k=5, ticker="NVDA")} == {1}
