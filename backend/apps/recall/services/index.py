from __future__ import annotations

from django.contrib.postgres.search import SearchVector

from apps.recall.embeddings import MODEL_NAME, embed
from apps.recall.models import RecallDocument
from apps.recall.text import build_text, content_hash, extract_tickers


def _source(kind, object_id):
    if kind == "thesis":
        from apps.thesis.models import Thesis

        return Thesis.objects.filter(id=object_id).first()
    if kind == "journal":
        from apps.thesis.models import DecisionJournalEntry

        return DecisionJournalEntry.objects.filter(id=object_id).first()
    if kind == "postmortem":
        from apps.thesis.models import PostMortem

        return PostMortem.objects.filter(id=object_id).first()
    if kind == "snapshot":
        from apps.snapshots.models import Snapshot

        return Snapshot.objects.filter(id=object_id).first()
    from apps.threads.models import Message

    return Message.objects.filter(id=object_id).first()  # message / observation


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
    """Yield (kind, object_id) for indexable sources not current in RecallDocument."""
    from apps.snapshots.models import Snapshot
    from apps.thesis.models import DecisionJournalEntry, PostMortem, Thesis
    from apps.threads.models import Message

    seen = {(k, o) for k, o in RecallDocument.objects.values_list("kind", "object_id")}
    out, n = [], 0

    def add(kind, ids):
        nonlocal n
        for i in ids:
            if (kind, i) not in seen and n < cap:
                out.append((kind, i))
                n += 1

    add(
        "message",
        Message.objects.filter(role="assistant", status="done").values_list("id", flat=True),
    )
    add("snapshot", Snapshot.objects.filter(status="ready").values_list("id", flat=True))
    add("thesis", Thesis.objects.values_list("id", flat=True))
    add("journal", DecisionJournalEntry.objects.values_list("id", flat=True))
    add(
        "postmortem",
        PostMortem.objects.filter(status="done").values_list("id", flat=True),
    )
    return out
