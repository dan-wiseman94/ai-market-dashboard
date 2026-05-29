from celery import shared_task

from apps.recall.services.index import index_one, pending


@shared_task(name="recall.index_document")
def index_document(kind: str, object_id: int) -> None:
    index_one(kind, object_id)


@shared_task(name="recall.index_pending")
def index_pending() -> dict:
    items = pending(cap=200)
    for kind, oid in items:
        index_document.delay(kind, oid)
    return {"dispatched": len(items)}
