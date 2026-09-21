from celery import shared_task

from apps.recall.services.index import index_one, pending, reconcile

# Upper bound on one backfill: large enough to clear a fresh install in a single
# press, bounded so one request can't flood the broker.
BACKFILL_CAP = 10_000


@shared_task(name="recall.index_document")
def index_document(kind: str, object_id: int) -> None:
    index_one(kind, object_id)


def _dispatch_pending(cap: int) -> dict:
    items = pending(cap=cap)
    for kind, oid in items:
        index_document.delay(kind, oid)
    # Reconcile the other direction: drop docs whose source was deleted (no FK to cascade).
    removed = reconcile()
    return {"dispatched": len(items), "reconciled": removed}


@shared_task(name="recall.index_pending")
def index_pending() -> dict:
    return _dispatch_pending(200)


@shared_task(name="recall.backfill")
def backfill(cap: int = BACKFILL_CAP) -> dict:
    """On-demand catch-up over the whole un-indexed backlog, queued from
    POST /api/recall/backfill/.

    Same fan-out as the 5-minute tick, just a bigger bite: one small index task per
    document, so no single task can hit the 600s soft time limit and a worker restart
    loses at most one document. Idempotent — ``pending()`` skips rows already in
    RecallDocument and ``index_one`` re-embeds only when the source text's hash
    changed, so repeated runs converge. Embeddings are local (fastembed): no provider
    spend, no cost cap.
    """
    return _dispatch_pending(cap)
