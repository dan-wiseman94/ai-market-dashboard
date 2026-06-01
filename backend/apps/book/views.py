from __future__ import annotations

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.book.models import BookSnapshot
from apps.book.serializers import BookSnapshotSerializer
from apps.book.services.compute import compute_and_store_book, current_book


class BookViewSet(ReadOnlyModelViewSet):
    queryset = BookSnapshot.objects.all()
    serializer_class = BookSnapshotSerializer

    @action(detail=False, methods=["get"])
    def current(self, request: Request):
        snap = current_book()
        if snap is None:
            return JsonResponse(None, safe=False)
        return Response(BookSnapshotSerializer(snap).data)

    @action(detail=False, methods=["post"])
    def recompute(self, request: Request) -> Response:
        return Response(BookSnapshotSerializer(compute_and_store_book()).data)
