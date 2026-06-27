from __future__ import annotations

from django.contrib.postgres.search import SearchVector

from apps.recall.embeddings import MODEL_NAME, embed
from apps.recall.models import RecallDocument
from apps.recall.text import build_text, content_hash, extract_tickers


def _source_model(kind):
    if kind == "thesis":
        from apps.thesis.models import Thesis

        return Thesis
    if kind == "journal":
        from apps.thesis.models import DecisionJournalEntry

        return DecisionJournalEntry
    if kind == "postmortem":
        from apps.thesis.models import PostMortem

        return PostMortem
    if kind == "snapshot":
        from apps.snapshots.models import Snapshot

        return Snapshot
    from apps.threads.models import Message

    return Message  # message / observation


def _source(kind, object_id):
    return _source_model(kind).objects.filter(id=object_id).first()


def _source_created_at(obj):
    return getattr(obj, "created_at", None) or getattr(obj, "captured_at", None)


def index_one(kind: str, object_id: int) -> None:
    obj = _source(kind, object_id)
    if obj is None:
        return
    text = build_text(kind, obj) or ""
    h = content_hash(text)
    existing = RecallDocument.objects.filter(kind=kind, object_id=object_id).first()
    if existing and existing.content_hash == h and existing.embedding is not None:
        return  # unchanged + already embedded
    vec = embed([text])
    embedding = vec[0] if vec else None
    doc, _ = RecallDocument.objects.update_or_create(
        kind=kind,
        object_id=object_id,
        defaults=dict(
            text=text,
            embedding=embedding,
            embedding_model=MODEL_NAME if embedding is not None else "",
            tickers=extract_tickers(kind, obj),
            source_created_at=_source_created_at(obj),
            content_hash=h,
        ),
    )
    RecallDocument.objects.filter(pk=doc.pk).update(search=SearchVector("text", config="english"))


def pending(*, cap: int = 200):
    """Return up to ``cap`` (kind, object_id) for indexable sources not yet indexed.

    Already-indexed rows are excluded **at the DB** (``NOT IN`` the per-kind
    ``RecallDocument.object_id`` set) and each source is taken newest-first with a
    ``LIMIT``, so the work scales with the (usually small) un-indexed backlog rather
    than total history — no full-table ``seen`` set materialized on every tick.
    """
    from apps.snapshots.models import Snapshot
    from apps.thesis.models import DecisionJournalEntry, PostMortem, Thesis
    from apps.threads.models import Message

    out: list[tuple[str, int]] = []

    def add(kind, qs):
        remaining = cap - len(out)
        if remaining <= 0:
            return
        indexed = RecallDocument.objects.filter(kind=kind).values_list("object_id", flat=True)
        fresh = qs.exclude(id__in=indexed).order_by("-id").values_list("id", flat=True)[:remaining]
        out.extend((kind, i) for i in fresh)

    add("message", Message.objects.filter(role="assistant", status="done"))
    add("snapshot", Snapshot.objects.filter(status="ready"))
    add("thesis", Thesis.objects.all())
    add("journal", DecisionJournalEntry.objects.all())
    add("postmortem", PostMortem.objects.filter(status="done"))
    return out


def reconcile() -> int:
    """Delete RecallDocument rows whose source object no longer exists, returning the count.

    RecallDocument keys its source as a generic ``(kind, object_id)`` pair with NO
    ForeignKey, and the index path only ever adds/updates — so deleting a source
    (a Message cascades with its Thread; Thesis/Snapshot have DELETE endpoints) would
    otherwise leave a stale row that keeps scoring in semantic + keyword recall, letting
    the Coach quote text from an object the user has since deleted. This is the reconcile
    half, run alongside index_pending. Batched: 2 reads + 1 delete per present kind.
    """
    deleted = 0
    for kind in RecallDocument.objects.values_list("kind", flat=True).distinct():
        doc_ids = set(RecallDocument.objects.filter(kind=kind).values_list("object_id", flat=True))
        live = set(_source_model(kind).objects.filter(id__in=doc_ids).values_list("id", flat=True))
        orphans = doc_ids - live
        if orphans:
            n, _ = RecallDocument.objects.filter(kind=kind, object_id__in=orphans).delete()
            deleted += n
    return deleted
