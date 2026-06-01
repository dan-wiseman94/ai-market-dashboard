from __future__ import annotations

from celery import shared_task

from apps.book.services.compute import compute_and_store_book


@shared_task(name="book.snapshot_daily")
def snapshot_daily() -> int:
    """Persist one daily BookSnapshot. The daily claim lives in compute_and_store_book."""
    snap = compute_and_store_book()
    return snap.id
