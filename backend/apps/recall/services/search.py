from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import CosineDistance

from apps.recall.embeddings import embed
from apps.recall.models import RecallDocument

_LINKS = {
    "message": "/threads",
    "snapshot": "/snapshots",
    "thesis": "/theses",
    "journal": "/theses",
    "postmortem": "/theses",
    "observation": "/threads",
}


def _hit(d) -> dict:
    return {
        "kind": d.kind,
        "object_id": d.object_id,
        "snippet": (d.text or "")[:280],
        "source_created_at": d.source_created_at,
        "tickers": d.tickers,
        "link": f"{_LINKS.get(d.kind, '/recall')}/{d.object_id}",
    }


def _filtered(qs, kinds, ticker):
    if kinds:
        qs = qs.filter(kind__in=kinds)
    if ticker:
        qs = qs.filter(tickers__contains=[ticker.upper()])
    return qs


def search(q: str, *, k: int = 10, kinds=None, ticker=None) -> list[dict]:
    vec = embed([q])
    qs = _filtered(RecallDocument.objects.all(), kinds, ticker)
    if vec:
        qs = qs.filter(embedding__isnull=False).order_by(CosineDistance("embedding", vec[0]))
    else:
        sq = SearchQuery(q, config="english")
        qs = qs.annotate(rank=SearchRank("search", sq)).filter(search=sq).order_by("-rank")
    return [_hit(d) for d in qs[:k]]


def mode() -> str:
    return "semantic" if embed(["probe"]) else "keyword"


def related(kind: str, object_id: int, *, k: int = 5) -> list[dict]:
    seed = RecallDocument.objects.filter(
        kind=kind, object_id=object_id, embedding__isnull=False
    ).first()
    if seed is None:
        return []
    qs = (
        RecallDocument.objects.filter(embedding__isnull=False)
        .exclude(pk=seed.pk)
        .order_by(CosineDistance("embedding", seed.embedding))
    )
    return [_hit(d) for d in qs[:k]]


def related_to_ticker(ticker: str, *, k: int = 5) -> list[dict]:
    qs = RecallDocument.objects.filter(tickers__contains=[ticker.upper()]).order_by(
        "-source_created_at"
    )
    return [_hit(d) for d in qs[:k]]


def related_to_situation(ticker: str, query: str, *, k: int = 3, kinds=None) -> list[dict]:
    """Situation-seeded, ticker-scoped semantic recall.

    Thin wrapper over :func:`search`: scopes to ``ticker``, optionally filters to
    ``kinds``, and bounds results to ``k``. Returns ``[]`` for an empty ticker and
    degrades exactly as ``search`` (semantic -> FTS -> empty). Returns the same
    dict-hit shape ``search`` does.
    """
    if not ticker:
        return []
    return search(query or ticker, k=k, kinds=kinds, ticker=ticker)
