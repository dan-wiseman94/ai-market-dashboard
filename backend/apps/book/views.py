from __future__ import annotations

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.book.models import BookSnapshot
from apps.book.serializers import BookSnapshotSerializer, BookSnapshotTrendSerializer
from apps.book.services.compute import compute_and_store_book, current_book

# The book gains one row per day, so an unbounded history grows without end.
_DEFAULT_HISTORY = 90
_MAX_HISTORY = 730


class BookViewSet(ReadOnlyModelViewSet):
    queryset = BookSnapshot.objects.all()
    serializer_class = BookSnapshotSerializer

    def get_serializer_class(self):
        """The list is a trend curve, the detail is the full X-ray."""
        return BookSnapshotTrendSerializer if self.action == "list" else BookSnapshotSerializer

    def get_queryset(self):
        """``GET /api/book/`` — history for a trend view.

        Newest-first (the model's own ordering) and capped; a chart reverses the
        rows itself. ``?since=``/``?until=`` filter on ``as_of_date``, ``?limit=``
        caps the window (clamped to ``_MAX_HISTORY``), and ``?order=asc`` returns
        them oldest-first instead. A non-numeric ``limit`` falls back to the
        default rather than 500-ing.
        """
        qs = BookSnapshot.objects.all()
        if self.action != "list":
            return qs
        p = self.request.query_params
        if p.get("since"):
            qs = qs.filter(as_of_date__gte=p["since"])
        if p.get("until"):
            qs = qs.filter(as_of_date__lte=p["until"])
        if p.get("order") == "asc":
            qs = qs.order_by("as_of_date")
        try:
            limit = int(p.get("limit", _DEFAULT_HISTORY))
        except (TypeError, ValueError):
            limit = _DEFAULT_HISTORY
        return qs[: max(1, min(limit, _MAX_HISTORY))]

    @action(detail=False, methods=["get"])
    def current(self, request: Request):
        snap = current_book()
        if snap is None:
            return JsonResponse(None, safe=False)
        return Response(BookSnapshotSerializer(snap).data)

    @action(detail=False, methods=["post"])
    def recompute(self, request: Request) -> Response:
        return Response(BookSnapshotSerializer(compute_and_store_book()).data)
