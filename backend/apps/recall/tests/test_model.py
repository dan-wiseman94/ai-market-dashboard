import pytest

from apps.recall.models import RecallDocument


@pytest.mark.django_db
def test_recall_document_roundtrip():
    d = RecallDocument.objects.create(
        kind="thesis",
        object_id=1,
        text="NVDA bullish into earnings",
        embedding=[0.1] * 384,
        embedding_model="bge-small",
        tickers=["NVDA"],
        content_hash="abc",
    )
    d.refresh_from_db()
    assert d.kind == "thesis" and len(d.embedding) == 384 and d.tickers == ["NVDA"]


@pytest.mark.django_db
def test_unique_kind_object():
    RecallDocument.objects.create(kind="thesis", object_id=1, text="x", content_hash="h")
    with pytest.raises(Exception):  # noqa: B017 - DB uniqueness error type varies by backend
        RecallDocument.objects.create(kind="thesis", object_id=1, text="y", content_hash="h2")
