from __future__ import annotations

from apps.book.models import BookSnapshot


def current_book() -> BookSnapshot | None:
    return BookSnapshot.objects.order_by("-created_at").first()
